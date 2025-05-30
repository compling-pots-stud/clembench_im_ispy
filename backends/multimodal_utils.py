"""
Util functions for multimodal models.
"""

from typing import List, Dict, Tuple, Any
import math
import numpy as np
import torch
import torchvision.transforms as T
from PIL import Image
from torchvision.transforms.functional import InterpolationMode
from transformers.image_utils import load_image
import requests
from io import BytesIO
from transformers.models.qwen2_vl.image_processing_qwen2_vl import Qwen2VLImageProcessor
from wepoints.utils.images import Qwen2ImageProcessorForPOINTSV15
from jinja2 import Template

"""
##### INTERNVL2 TYPE MODELS #####
"""

IMAGENET_MEAN = (0.485, 0.456, 0.406)
IMAGENET_STD = (0.229, 0.224, 0.225)


def generate_history_internvl2(messages: List[str]) -> Tuple[List[Tuple], str]:
    """
    Separates the history and query from the list of messages in the current game instance.
    Compatible with InternVL2 and Nvidia NVLM models.

    Args:
        messages: A list containing user messages, system messages or assistant responses.

    Returns:
        A list of tuples containing the history and a user message string, passed to the model in the current game instance.

    Raises:
        ValueError: if msg['role'] is different than 'user', 'system', or 'assistant'.
    """

    history = []
    for msg in messages:
        if msg['role'] == 'system':
            continue # Skip the system message, Not passed to the model. Ref - https://huggingface.co/OpenGVLab/InternVL2-40B
        elif msg['role'] == 'user':
            if 'image' in msg:
                user_message = f"<image>\n{msg['content']}" # Add <image> token if image is passed in this instance.
            else:
                user_message = msg['content']
        elif msg['role'] == 'assistant':
            history.append((user_message, msg['content']))
        else:
            raise ValueError(f"Invalid role: {msg['role']}. Expected 'user', 'system', or 'assistant'.")

    return history, user_message


def split_model(model_name):
    """
    Splits the model across available GPUs based on the model name.

    Args:
        model_name (str): The name of the model to be split.
                          Expected values include 'InternVL2-1B', 'InternVL2-2B',
                          'InternVL2-4B', 'InternVL2-8B', 'InternVL2-26B',
                          'InternVL2-40B', 'InternVL2-Llama3-76B'.

    Returns:
        dict: A mapping of model layers to GPU indices.
    """
    device_map = {}
    world_size = torch.cuda.device_count()
    num_layers = {
        'InternVL2-1B': 24, 'InternVL2-2B': 24, 'InternVL2-4B': 32, 'InternVL2-8B': 32, 'InternVL2-8B-MPO': 32,
        'InternVL2-26B': 48, 'InternVL2-40B': 60, 'InternVL2-Llama3-76B': 80}[model_name]
    # Since the first GPU will be used for ViT, treat it as half a GPU.
    num_layers_per_gpu = math.ceil(num_layers / (world_size - 0.5))
    num_layers_per_gpu = [num_layers_per_gpu] * world_size
    num_layers_per_gpu[0] = math.ceil(num_layers_per_gpu[0] * 0.5)
    layer_cnt = 0
    for i, num_layer in enumerate(num_layers_per_gpu):
        for j in range(num_layer):
            device_map[f'language_model.model.layers.{layer_cnt}'] = i
            layer_cnt += 1
    device_map['vision_model'] = 0
    device_map['mlp1'] = 0
    device_map['language_model.model.tok_embeddings'] = 0
    device_map['language_model.model.embed_tokens'] = 0
    device_map['language_model.output'] = 0
    device_map['language_model.model.norm'] = 0
    device_map['language_model.lm_head'] = 0
    device_map[f'language_model.model.layers.{num_layers - 1}'] = 0

    return device_map

def build_transform(input_size):
    """Builds a transformation pipeline for image preprocessing.

    Args:
        input_size (int): The size to which the image will be resized.

    Returns:
        torchvision.transforms.Compose: A composed transform for the image.
    """
    MEAN, STD = IMAGENET_MEAN, IMAGENET_STD
    transform = T.Compose([
        T.Lambda(lambda img: img.convert('RGB') if img.mode != 'RGB' else img),
        T.Resize((input_size, input_size), interpolation=InterpolationMode.BICUBIC),
        T.ToTensor(),
        T.Normalize(mean=MEAN, std=STD)
    ])
    return transform

def find_closest_aspect_ratio(aspect_ratio, target_ratios, width, height, image_size):
    """Finds the closest aspect ratio from a set of target ratios.

    Args:
        aspect_ratio (float): The aspect ratio of the original image.
        target_ratios (list): A list of target aspect ratios.
        width (int): The width of the original image.
        height (int): The height of the original image.
        image_size (int): The size of the image for comparison.

    Returns:
        tuple: The best aspect ratio found.
    """
    best_ratio_diff = float('inf')
    best_ratio = (1, 1)
    area = width * height
    for ratio in target_ratios:
        target_aspect_ratio = ratio[0] / ratio[1]
        ratio_diff = abs(aspect_ratio - target_aspect_ratio)
        if ratio_diff < best_ratio_diff:
            best_ratio_diff = ratio_diff
            best_ratio = ratio
        elif ratio_diff == best_ratio_diff:
            if area > 0.5 * image_size * image_size * ratio[0] * ratio[1]:
                best_ratio = ratio
    return best_ratio

def dynamic_preprocess(image, min_num=1, max_num=12, image_size=448, use_thumbnail=False):
    """Processes the image to fit the closest aspect ratio and splits it into blocks.

    Args:
        image (PIL.Image): The image to be processed.
        min_num (int): Minimum number of blocks.
        max_num (int): Maximum number of blocks.
        image_size (int): The size of the image.
        use_thumbnail (bool): Whether to create a thumbnail.

    Returns:
        list: A list of processed image blocks.
    """
    orig_width, orig_height = image.size
    aspect_ratio = orig_width / orig_height

    # calculate the existing image aspect ratio
    target_ratios = set(
        (i, j) for n in range(min_num, max_num + 1) for i in range(1, n + 1) for j in range(1, n + 1) if
        i * j <= max_num and i * j >= min_num)
    target_ratios = sorted(target_ratios, key=lambda x: x[0] * x[1])

    # find the closest aspect ratio to the target
    target_aspect_ratio = find_closest_aspect_ratio(
        aspect_ratio, target_ratios, orig_width, orig_height, image_size)

    # calculate the target width and height
    target_width = image_size * target_aspect_ratio[0]
    target_height = image_size * target_aspect_ratio[1]
    blocks = target_aspect_ratio[0] * target_aspect_ratio[1]

    # resize the image
    resized_img = image.resize((target_width, target_height))
    processed_images = []
    for i in range(blocks):
        box = (
            (i % (target_width // image_size)) * image_size,
            (i // (target_width // image_size)) * image_size,
            ((i % (target_width // image_size)) + 1) * image_size,
            ((i // (target_width // image_size)) + 1) * image_size
        )
        # split the image
        split_img = resized_img.crop(box)
        processed_images.append(split_img)
    assert len(processed_images) == blocks
    if use_thumbnail and len(processed_images) != 1:
        thumbnail_img = image.resize((image_size, image_size))
        processed_images.append(thumbnail_img)
    return processed_images

def load_internvl2_image(image_file, input_size=448, max_num=12):
    """Loads an image file and applies transformations.

    Args:
        image_file (str): The path to the image file.
        input_size (int): The size to which the image will be resized.
        max_num (int): Maximum number of blocks to create.

    Returns:
        torch.Tensor: A tensor containing the pixel values of the processed images.
    """
    if image_file.startswith("http"):
        response = requests.get(image_file)
        image = Image.open(BytesIO(response.content)).convert('RGB')
    else:
        image = Image.open(image_file).convert('RGB')

    transform = build_transform(input_size=input_size)
    images = dynamic_preprocess(image, image_size=input_size, use_thumbnail=True, max_num=max_num)
    pixel_values = [transform(image) for image in images]
    pixel_values = torch.stack(pixel_values)
    return pixel_values

def get_internvl2_image(messages: List[str], device: str):
    """
    Extracts the last user message containing image data and loads the corresponding images.

    Args:
        messages (List[str]): A list of message dictionaries containing user, system, and assistant messages.
        device (str): The device to which the image tensors will be moved (e.g., 'cuda' or 'cpu').

    Returns:
        torch.Tensor: A tensor containing the pixel values of the processed images.

    Raises:
        ValueError: If no user message is found.
    """
    # Get last user message
    last_user_message = None
    for i in range(len(messages)):
        index = len(messages) - i - 1
        # Find last user message
        if messages[index]['role'] == 'user':
            last_user_message = messages[index]

    if last_user_message is None:
        raise ValueError("No user message found in the provided messages.")
    else:
        if len(last_user_message['image']) > 1:
            pixel_values = load_internvl2_image(last_user_message['image'][0], max_num=12).to(torch.bfloat16).to(device)
            for i in range(1, len(last_user_message['image'])):
                pixel_values1 = load_internvl2_image(last_user_message['image'][i], max_num=12).to(torch.bfloat16).to(device)
                pixel_values = torch.cat((pixel_values, pixel_values1), dim=0)
        else:
            pixel_values = load_internvl2_image(last_user_message['image'][0], max_num=12).to(torch.bfloat16).to(device)

    return pixel_values

def generate_internvl2_prompt_text(messages: List[str], **prompt_kwargs) -> str:
    """Generates input text for the InternVL2 model from a list of messages.

    Args:
        messages (List[str]): A list of message dictionaries containing user, system, and assistant messages.

    Returns:
        str: The concatenated prompt text generated from the message history and the last user question.
    """
    prompt_text = ""
    history, question = generate_history_internvl2(messages=messages)
    if history:
        for t in history:
            prompt_text += t[0] + t[1]
    prompt_text += question
    return prompt_text

def generate_internvl2_response(**response_kwargs) -> str:
    """Generates a response from the InternVL2 model based on the provided messages and configuration.

    Args:
        **response_kwargs: A dictionary containing the following keys:
            - messages (List[str]): A list of message dictionaries.
            - device (str): The device to which the image tensors will be moved (e.g., 'cuda' or 'cpu').
            - max_tokens (int): The maximum number of tokens to generate.
            - model: The model instance used for generating responses.
            - processor: The processor instance used for processing images.

    Returns:
        str: The generated response from the model.
    """
    messages = response_kwargs['messages']
    device = response_kwargs['device']
    max_tokens = response_kwargs['max_tokens']
    model = response_kwargs['model']
    processor = response_kwargs['processor']

    images = get_internvl2_image(messages=messages, device=device)
    history, question = generate_history_internvl2(messages=messages)
    if not history:
        history = None
    generation_config = dict(max_new_tokens=max_tokens, do_sample=True)
    generated_response, _ = model.chat(processor, images, question, generation_config,
                                                     history=history, return_history=True)

    return generated_response


"""
##### LLAVA TYPE MODELS #####
Compatible models - LLaVA 1.5, LLaVA 1.6, Idefics3
"""

def generate_llava_messages(messages: List[str]) -> Tuple[List, List]:
    """Generates LLAVA messages and image paths from a list of messages.

    Args:
        messages (List[str]): A list of message dictionaries containing user, system, and assistant messages.

    Returns:
        Tuple[List, List]: A tuple containing:
            - A list of formatted LLAVA messages.
            - A list of image paths extracted from the messages.
    """
    llava_messages = []
    image_paths = []
    for message in messages:
        message_dict = {}
        message_dict['content'] = []

        if message['role'] == 'user':
            message_dict['role'] = 'user'
            if 'image' in message:
                if isinstance(message['image'], str):
                    # Single image
                    message_dict['content'].append({"type": "image"})
                    image_paths.append(message['image'])
                elif isinstance(message['image'], list):
                    # List of images
                    for img in message['image']:
                        message_dict['content'].append({"type": "image"})
                        image_paths.append(img)
                else:
                    raise ValueError("Invalid image type in message - should be str or List[str]")

            # Add user text message at the end
            message_dict['content'].append({"type": "text", "text": message['content']})
            llava_messages.append(message_dict)

        elif message['role'] == 'assistant':
            message_dict['role'] = 'assistant'
            message_dict['content'].append({"type": "text", "text": message['content']})
            llava_messages.append(message_dict)

        elif message['role'] == 'system':
            continue # Skip System message
        else:
            raise ValueError(f"Invalid role: {message_dict['role']}. Expected 'user', 'system', or 'assistant'.")

    last_user_message = llava_messages[-1]
    if last_user_message['role'] == 'user':
        content = last_user_message['content']
        contains_image = False
        for val in content:
            if val["type"] == "image":
                contains_image = True

        if not contains_image: # Pass a blank image
            blank_image = Image.new('RGB', (128, 128), color='white')
            image_paths.append(blank_image)
            llava_messages[-1]['content'].append({"type": "image"})

    return llava_messages, image_paths

def generate_llava_prompt_text(messages: List[str], **prompt_kwargs) -> str:
    """Generates a prompt text for LLAVA from a list of messages.

    Args:
        messages (List[str]): A list of message dictionaries containing user, system, and assistant messages.
        **prompt_kwargs: Additional keyword arguments for processing.

    Returns:
        str: The generated prompt text for LLAVA.
    """
    llava_messages, _ = generate_llava_messages(messages=messages)
    processor = prompt_kwargs['processor']
    prompt = processor.apply_chat_template(llava_messages, add_generation_prompt=True)

    return prompt

def generate_llava_response(**response_kwargs) -> str:
    """Generates a response from the LLAVA model based on the provided messages and configuration.

    Args:
        **response_kwargs: A dictionary containing the following keys:
            - messages (List[str]): A list of message dictionaries.
            - device (str): The device to which the image tensors will be moved (e.g., 'cuda' or 'cpu').
            - max_tokens (int): The maximum number of tokens to generate.
            - model: The model instance used for generating responses.
            - processor: The processor instance used for processing images.

    Returns:
        str: The generated response from the LLAVA model.
    """
    messages = response_kwargs['messages']
    device = response_kwargs['device']
    max_tokens = response_kwargs['max_tokens']
    model = response_kwargs['model']
    processor = response_kwargs['processor']
    do_sample = response_kwargs['do_sample']

    llava_messages, image_paths = generate_llava_messages(messages=messages)
    prompt = processor.apply_chat_template(llava_messages, add_generation_prompt=True)

    # Process images
    processed_images = []
    for image in image_paths:
        if type(image) == str:
            processed_images.append(load_image(image))
        else:
            processed_images.append(image)

    inputs = processor(images=processed_images, text=prompt, return_tensors='pt').to(device)

    output = model.generate(**inputs, max_new_tokens=max_tokens, do_sample=do_sample)
    response = processor.decode(output[0][2:], skip_special_tokens=True)

    return response


"""
##### IDEFICS TYPE MODELS #####
"""

def generate_idefics_prompt_text(messages: List[str], **prompt_kwargs) -> str:
    """Generates a prompt text from a list of messages for the IDEFICS model.

    Args:
        messages (List[str]): A list of message dictionaries containing user, system, and assistant messages.
        **prompt_kwargs: Additional keyword arguments for processing.

    Returns:
        str: The concatenated prompt text generated from the message history.
    """
    prompt_text = ""
    for msg in messages:
        if msg['role'] == 'system':
            continue  # Skip system message. Ref - https://huggingface.co/HuggingFaceM4/idefics-9b-instruct
        elif msg['role'] == 'user':
            prompt_text += f" User: {msg['content']} "
            if 'image' in msg:
                if len(msg['image']) > 1:
                    for img in msg['image']:
                        prompt_text += img
                else:
                    prompt_text += msg['image'][0]
            prompt_text += "<end_of_utterance>"
        elif msg['role'] == 'assistant':
            prompt_text += f" Assistant: {msg['content']} <end_of_utterance>"
        else:
            raise ValueError(f"Invalid role: {msg['role']}. Expected 'user', 'system', or 'assistant'.")

    return prompt_text

def generate_idefics_response(**response_kwargs) -> str:
    """Generates a response from the IDEFICS model based on the provided messages and configuration.

    Args:
        **response_kwargs: A dictionary containing the following keys:
            - messages (List[str]): A list of message dictionaries.
            - device (str): The device to which the image tensors will be moved (e.g., 'cuda' or 'cpu').
            - max_tokens (int): The maximum number of tokens to generate.
            - model: The model instance used for generating responses.
            - processor: The processor instance used for processing images.

    Returns:
        str: The generated response from the IDEFICS model.
    """
    messages = response_kwargs['messages']
    device = response_kwargs['device']
    max_tokens = response_kwargs['max_tokens']
    model = response_kwargs['model']
    processor = response_kwargs['processor']

    input_messages = []
    for msg in messages:
        if msg['role'] == 'system':
            continue  # Skip system message. Ref - https://huggingface.co/HuggingFaceM4/idefics-9b-instruct
        elif msg['role'] == 'user':
            input_messages.append(f"\nUser: {msg['content']}")
            if 'image' in msg:
                if len(msg['image']) > 1:
                    for img in msg['image']:
                        loaded_image = load_image(img)
                        input_messages.append(loaded_image)
                else:
                    loaded_image = load_image(msg['image'][0])
                    input_messages.append(loaded_image)
            input_messages.append("<end_of_utterance>")
        elif msg['role'] == 'assistant':
            input_messages.append(f"\nAssistant: {msg['content']} <end_of_utterance>")
        else:
            raise ValueError(f"Invalid role: {msg['role']}. Expected 'user', 'system', or 'assistant'.")

    # --batched mode
    inputs = processor(input_messages, add_end_of_utterance_token=False, return_tensors="pt").to(device)

    # Generation args
    exit_condition = processor.tokenizer("<end_of_utterance>", add_special_tokens=False).input_ids
    bad_words_ids = processor.tokenizer(["<image>", "<fake_token_around_image>"], add_special_tokens=False).input_ids

    generated_ids = model.generate(**inputs, eos_token_id=exit_condition, bad_words_ids=bad_words_ids, max_length=max_tokens)
    generated_text = processor.batch_decode(generated_ids, skip_special_tokens=True)

    return generated_text[0]



"""
##### QWEN TYPE MODELS #####
"""

def generate_qwen_vl_messages(messages: List[str]) -> Tuple[List, List]:
    """Generates Qwen-VL formatted messages and image inputs from a list of messages.

    Args:
        messages (List[Dict]): A list of message dictionaries containing user, assistant, and optionally images.

    Returns:
        Tuple[List, List]: A tuple containing:
            - A list of Qwen-VL formatted messages.
            - A list of image inputs extracted from the messages.
    """
    qwen_messages = []
    image_inputs = []

    for message in messages:
        message_dict = {}
        message_dict['role'] = message['role']
        message_dict['content'] = []

        if message['role'] == 'user':
            if 'image' in message:
                if isinstance(message['image'], str):
                    # Single image
                    message_dict['content'].append({"type": "image"})
                    image_inputs.append(message['image'])
                elif isinstance(message['image'], list):
                    # Multiple images
                    for img in message['image']:
                        message_dict['content'].append({"type": "image"})
                        image_inputs.append(img)
                else:
                    raise ValueError("Invalid image type in message - should be str or List[str]")

            # Add user text
            if 'content' in message:
                message_dict['content'].append({"type": "text", "text": message['content']})

            qwen_messages.append(message_dict)

        elif message['role'] == 'assistant':
            # Add assistant response
            message_dict['content'].append({"type": "text", "text": message['content']})
            qwen_messages.append(message_dict)

        elif message['role'] == 'system':
            # Qwen-VL does not process system messages directly, so skip
            continue
        else:
            raise ValueError(f"Invalid role: {message['role']}. Expected 'user', 'assistant', or 'system'.")

    if qwen_messages and qwen_messages[-1]['role'] == 'user':
        content = qwen_messages[-1]['content']
        contains_image = any(item["type"] == "image" for item in content)

        if not contains_image:
            blank_image = Image.new("RGB", (128, 128), color="white")
            image_inputs.append(blank_image)
            qwen_messages[-1]['content'].append({"type": "image"})

    return qwen_messages, image_inputs

def generate_qwen_vl_prompt_text(messages: List[str], **prompt_kwargs) -> str:
    qwen_messages, _ = generate_qwen_vl_messages(messages=messages)
    processor = prompt_kwargs['processor']
    prompt = processor.apply_chat_template(qwen_messages, add_generation_prompt=True)

    return prompt


def generate_qwen_vl_response(**response_kwargs) -> str:
    """Generates a response from the Qwen-vl model based on the provided messages and configuration.

    Args:
        **response_kwargs: A dictionary containing the following keys:
            - messages (List[str]): A list of message dictionaries.
            - device (str): The device to which the image tensors will be moved (e.g., 'cuda' or 'cpu').
            - max_tokens (int): The maximum number of tokens to generate.
            - model: The model instance used for generating responses.
            - processor: The processor instance used for processing images.

    Returns:
        str: The generated response from the LLAVA model.
    """

    messages = response_kwargs['messages']
    device = response_kwargs['device']
    max_tokens = response_kwargs['max_tokens']
    model = response_kwargs['model']
    processor = response_kwargs['processor']
    do_sample = response_kwargs['do_sample']

    qwen_messages, image_paths = generate_qwen_vl_messages(messages=messages)
    prompt = processor.apply_chat_template(qwen_messages, add_generation_prompt=True)

    # Process images
    processed_images = []
    for image in image_paths:
        if type(image) == str:
            processed_images.append(load_image(image))
        else:
            processed_images.append(image)

    inputs = processor(images=processed_images, text=prompt, return_tensors='pt').to(device)

    output_ids = model.generate(**inputs, max_new_tokens=max_tokens, do_sample=do_sample)
    generated_ids = [output_ids[len(input_ids):] for input_ids, output_ids in zip(inputs.input_ids, output_ids)]

    response = processor.batch_decode(generated_ids, skip_special_tokens=True, clean_up_tokenization_spaces=True)

    return response[0]


"""
##### OVIS GEMMA MODELS #####
"""

def generate_ovis_messages(messages: List[Dict], **prompt_kwargs) -> Tuple[List, List]:
    """Generates Ovis-1.6 Gemma 9b formatted messages and image inputs from a list of messages.




    Args:
        messages (List[Dict]): A list of message dictionaries containing user, assistant, and optionally images.

    Returns:
        Tuple[List, List]: A tuple containing:
            - A list of Qwen-VL formatted messages.
            - A list of image inputs extracted from the messages.
    """

    # Ovis uses gpt and human for asistant and  user.
    # there is a preprocessing script that later on translates this
    # into standard roles used by gemma.
    # content is provided as a str under value key inside the conversation/msg dict.
    # conversation needs to be a list of dictionaries.

    ovis_messages = []
    image_inputs = []

    for message in messages:
        message_dict = {}
        value = ""

        if message.get('role') == 'system':
            continue

        if message.get('role') == 'user':
            message_dict['from'] = 'human'

            # Check if the 'image' key exists and handle it accordingly
            image_field = message.get('image', None)
            if isinstance(image_field, str):
                value += '<image>\n'
                image_inputs.append(image_field)
            elif isinstance(image_field, list):
                for inx, val in enumerate(image_field):
                    value += f"Image {inx}: <image>\n"
                    image_inputs.append(val)
            else:
                # Create a blank image if no valid 'image' field is found
                blank_image = Image.new("RGB", (128, 128), color="white")
                image_inputs.append(blank_image)
                value += '<image>\n'

            if 'content' in message:
                value += message['content']

        if message.get('role') == 'assistant':
            message_dict['from'] = 'gpt'

            if 'content' in message:
                value += message['content']

        message_dict['value'] = value
        ovis_messages.append(message_dict)

    return ovis_messages, image_inputs

def generate_ovis_prompt(messages: List[str], **prompt_kwargs) -> str:
    model = prompt_kwargs['model']

    text_input, image_input = generate_ovis_messages(messages)
    processed_images = []
    for image in image_input:
        if type(image) == str:
            processed_images.append(load_image(image))
        else:
            processed_images.append(image)

    prompt, input_ids, pixel_values = model.preprocess_inputs(text_input, processed_images, return_labels=False)

    return prompt


def generate_ovis_response(**response_kwargs) -> str:
    """Generates a response from the Qwen-vl model based on the provided messages and configuration.

    Args:
        **response_kwargs: A dictionary containing the following keys:
            - messages (List[str]): A list of message dictionaries.
            - device (str): The device to which the image tensors will be moved (e.g., 'cuda' or 'cpu').
            - max_tokens (int): The maximum number of tokens to generate.
            - model: The model instance used for generating responses.
            - processor: The processor instance used for processing images.

    Returns:
        str: The generated response from the LLAVA model.
    """
    messages = response_kwargs['messages']
    device = response_kwargs['device']
    max_tokens = response_kwargs['max_tokens']
    model = response_kwargs['model']
    processor = response_kwargs['processor']
    do_sample = response_kwargs['do_sample']

    text_tokenizer = model.get_text_tokenizer()
    visual_tokenizer = model.get_visual_tokenizer()

    text_input, image_input = generate_ovis_messages(messages)

    processed_images = []
    for image in image_input:
        if type(image) == str:
            processed_images.append(load_image(image))
        else:
            processed_images.append(image)

    prompt, input_ids, pixel_values = model.preprocess_inputs(text_input, processed_images, return_labels=False)

    attention_mask = torch.ne(input_ids, text_tokenizer.pad_token_id)
    input_ids = input_ids.unsqueeze(0).to(device=device)
    attention_mask = attention_mask.unsqueeze(0).to(device=device)
    pixel_values = [pixel_values.to(dtype=visual_tokenizer.dtype, device=device)]

    # generate output
    with torch.inference_mode():
        gen_kwargs = dict(
            max_new_tokens=max_tokens,
            do_sample=do_sample,
            top_p=None,
            top_k=None,
            temperature=None,
            repetition_penalty=None,
            eos_token_id=model.generation_config.eos_token_id,
            pad_token_id=text_tokenizer.pad_token_id,
            use_cache=True
        )

        output_ids = model.generate(input_ids, pixel_values=pixel_values, attention_mask=attention_mask, **gen_kwargs)[0]
        response = text_tokenizer.decode(output_ids, skip_special_tokens=True)

        return response


"""
##### OVIS LLama MODELS #####
"""

def generate_ovis_l_messages(messages: List[Dict], **prompt_kwargs) -> Tuple[List, List]:
    """Generates Ovis-1.6 Gemma 9b formatted messages and image inputs from a list of messages.




    Args:
        messages (List[Dict]): A list of message dictionaries containing user, assistant, and optionally images.

    Returns:
        Tuple[List, List]: A tuple containing:
            - A list of Qwen-VL formatted messages.
            - A list of image inputs extracted from the messages.
    """

    # Ovis uses gpt and human for asistant and  user.
    # there is a preprocessing script that later on translates this
    # into standard roles used by gemma.
    # content is provided as a str under value key inside the conversation/msg dict.
    # conversation needs to be a list of dictionaries.

    ovis_messages = []
    image_inputs = []

    for message in messages:
        message_dict = {}
        value = ""

        if message.get('role') == 'system':
            continue

        if message.get('role') == 'user':
            message_dict['from'] = 'human'

            # Check if the 'image' key exists and handle it accordingly
            image_field = message.get('image', None)
            if isinstance(image_field, str):
                value += '<image>\n'
                image_inputs.append(image_field)
            elif isinstance(image_field, list):
                for inx, val in enumerate(image_field):
                    value += f"Image {inx}: <image>\n"
                    image_inputs.append(val)
            else:
                # Create a blank image if no valid 'image' field is found
                blank_image = Image.new("RGB", (128, 128), color="white")
                image_inputs.append(blank_image)
                value += '<image>\n'

            if 'content' in message:
                value += message['content']

        if message.get('role') == 'assistant':
            message_dict['from'] = 'gpt'

            if 'content' in message:
                value += message['content']

        message_dict['value'] = value
        ovis_messages.append(message_dict)

    return ovis_messages, image_inputs

def generate_ovis_l_prompt(messages: List[str], **prompt_kwargs) -> str:
    model = prompt_kwargs['model']
    text_tokenizer = model.get_text_tokenizer()
    visual_tokenizer = model.get_visual_tokenizer()
    conversation_formatter = model.get_conversation_formatter()

    text_input, image_input = generate_ovis_l_messages(messages)

    prompt, _, _ = conversation_formatter.format(text_input)

    return prompt


def generate_ovis_l_response(**response_kwargs) -> str:
    """Generates a response from the Qwen-vl model based on the provided messages and configuration.

    Args:
        **response_kwargs: A dictionary containing the following keys:
            - messages (List[str]): A list of message dictionaries.
            - device (str): The device to which the image tensors will be moved (e.g., 'cuda' or 'cpu').
            - max_tokens (int): The maximum number of tokens to generate.
            - model: The model instance used for generating responses.
            - processor: The processor instance used for processing images.

    Returns:
        str: The generated response from the LLAVA model.
    """
    messages = response_kwargs['messages']
    device = response_kwargs['device']
    max_tokens = response_kwargs['max_tokens']
    model = response_kwargs['model']
    processor = response_kwargs['processor']
    do_sample = response_kwargs['do_sample']

    text_tokenizer = model.get_text_tokenizer()
    visual_tokenizer = model.get_visual_tokenizer()
    conversation_formatter = model.get_conversation_formatter()

    text_input, image_input = generate_ovis_messages(messages)

    processed_images = []
    for image in image_input:
        if type(image) == str:
            processed_images.append(load_image(image))
        else:
            processed_images.append(image)


    prompt, input_ids, _ = conversation_formatter.format(text_input)
    input_ids = torch.unsqueeze(input_ids, dim=0).to(device=device)
    attention_mask = torch.ne(input_ids, text_tokenizer.pad_token_id).to(device=device)

    pixel_values = [visual_tokenizer.preprocess_image(processed_images[0]).to(
        dtype=visual_tokenizer.dtype, device=device)]

    # generate output
    with torch.inference_mode():
        gen_kwargs = dict(
            max_new_tokens=max_tokens,
            do_sample=do_sample,
            top_p=None,
            top_k=None,
            temperature=None,
            repetition_penalty=None,
            eos_token_id=model.generation_config.eos_token_id,
            pad_token_id=text_tokenizer.pad_token_id,
            use_cache=True
        )

        output_ids = model.generate(input_ids, pixel_values=pixel_values, attention_mask=attention_mask, **gen_kwargs)[0]
        response = text_tokenizer.decode(output_ids, skip_special_tokens=True)

        return response


"""
##### PIXTRAL TYPE MODELS #####
"""


def generate_pixtral_messages(messages: List[Dict], **prompt_kwargs) -> Tuple[List, List]:
    """
    Generates Pixtral-12b formatted messages and image inputs from a list of messages.

    Args:
        messages (List[Dict]): A list of message dictionaries containing 'role', 'content', and optionally 'image'.

    Returns:
        Tuple[List, List]: A tuple containing:
            - A list of Pixtral-12b formatted messages.
            - A list of image inputs extracted from the messages.
    """
    pixtral_messages = []
    image_inputs = []

    for message in messages:
        if message['role'] == 'system':
            continue
        if message['role'] == 'assistant':
            formatted_message= {"role": message["role"], "content" : message["content"]}

        else:
            formatted_message = {"role": message["role"], "content": []}

            if "content" in message:
                # Add text content
                formatted_message["content"].append({"type": "text", "content": message["content"]})

            if "image" in message:
                # Handle image content (both single and multiple images)
                if isinstance(message["image"], str):
                    formatted_message["content"].append({"type": "image"})
                    image_inputs.append(message["image"])
                elif isinstance(message["image"], list):
                    for img in message["image"]:
                        formatted_message["content"].append({"type": "image"})
                        image_inputs.append(img)
                else:
                    raise ValueError("Invalid image type in message - should be str or List[str]")

        pixtral_messages.append(formatted_message)

        # Ensure last user message has an image if required
        if pixtral_messages and pixtral_messages[-1]["role"] == "user":
            if not any(item["type"] == "image" for item in pixtral_messages[-1]["content"]):
                blank_image = Image.new("RGB", (128, 128), color="white")  # Placeholder blank image
                image_inputs.append(blank_image)
                pixtral_messages[-1]["content"].append({"type": "image"})

    return pixtral_messages, image_inputs

def generate_pixtral_prompt(messages: List[Dict], **prompt_kwargs) -> str:
    """
    Generates a prompt for Pixtral-12b based on input messages.

    Args:
        messages (List[Dict]): A list of messages.
        processor: The Pixtral-12b processor instance.

    Returns:
        str: The formatted prompt.
    """


    pixtral_messages, _ = generate_pixtral_messages(messages)

    processor = prompt_kwargs['processor']
    prompt = processor.apply_chat_template(pixtral_messages)

    return prompt


def generate_pixtral_response(**response_kwargs) -> str:
    """
    Generates a response from the Pixtral-12b model.

    Args:
        **response_kwargs: A dictionary containing:
            - messages (List[Dict]): Input messages.
            - device (str): Device for processing (e.g., 'cuda' or 'cpu').
            - max_tokens (int): Maximum number of tokens to generate.
            - model: Pixtral-12b model instance.
            - processor: Pixtral-12b processor instance.
            - do_sample (bool): Whether to sample during generation.

    Returns:
        str: The generated response.
    """
    messages = response_kwargs["messages"]
    device = response_kwargs["device"]
    max_tokens = response_kwargs["max_tokens"]
    model = response_kwargs["model"]
    processor = response_kwargs["processor"]
    do_sample = response_kwargs.get("do_sample", False)
    template_input = response_kwargs.get("template") # need to render template. There is a error in code. Must do

    pixtral_messages, image_paths = generate_pixtral_messages(messages=messages)
    prompt = processor.apply_chat_template(pixtral_messages)
    processed_images = []
    for image in image_paths:
        if type(image) == str:
            processed_images.append(load_image(image))
        else:
            processed_images.append(image)

    image_paths = processed_images
    inputs = processor(text=prompt, images=image_paths, return_tensors="pt").to(device)


    generate_ids = model.generate(**inputs, max_new_tokens=max_tokens, do_sample=do_sample)
    response = processor.batch_decode(generate_ids, skip_special_tokens=False, clean_up_tokenization_spaces=False)

    return response[0]


"""
##### Phi-3.5-Vision, Phi-3-vision-128k-instruct #####
"""

def generate_phi_messages(messages: List[Dict]) -> Tuple[List, List]:
    """
    Generates Pixtral-12b formatted messages and image inputs from a list of messages.

    Args:
        messages (List[Dict]): A list of message dictionaries containing 'role', 'content', and optionally 'image'.

    Returns:
        Tuple[List, List]: A tuple containing:
            - A list of Pixtral-12b formatted messages.
            - A list of image inputs extracted from the messages.
    """

    phi_messages = []
    image_inputs = []

    for message in messages:
        message_obj = {}
        if message['role'] == 'system':
            continue
        if message['role'] == 'user':
            message_obj['role'] = message['role']
            content = ''

            if 'image' in message:
                if isinstance(message["image"], str):
                    # message_obj["content"].append({"type": "image"})
                    image_inputs.append(message["image"])
                    content += '<|image_1|>\n'
                elif isinstance(message["image"], list):
                    for inx, img in enumerate(message["image"]):
                        # formatted_message["content"].append({"type": "image"})
                        image_inputs.append(img)
                        content += f'<|image_{inx}|>\n'
                else:
                    blank_image = Image.new("RGB", (128, 128), color="white")  # Placeholder blank image
                    content += '<|image_1|>\n'
                    image_inputs.append(blank_image)

            if "content" in message:
                content += message['content']
                message_obj['content'] = content

        if message['role'] == 'assistant':
            content = ''
            message_obj['role'] = message['role']

            if "content" in message:
                content += message['content']
                message_obj['content'] = content

        phi_messages.append(message_obj)

    return phi_messages, image_inputs

def generate_phi_prompt(messages: List[Dict], **prompt_kwargs) -> str:
    """
    Generates a prompt for Pixtral-12b based on input messages.

    Args:
        messages (List[Dict]): A list of messages.
        processor: The Pixtral-12b processor instance.

    Returns:
        str: The formatted prompt.
    """
    phi_messages, _ = generate_phi_messages(messages)
    processor = prompt_kwargs['processor']
    prompt = processor.apply_chat_template(phi_messages)

    return prompt

def generate_phi_response(**response_kwargs) -> str:
    """
    Generates a response from the Pixtral-12b model.

    Args:
        **response_kwargs: A dictionary containing:
            - messages (List[Dict]): Input messages.
            - device (str): Device for processing (e.g., 'cuda' or 'cpu').
            - max_tokens (int): Maximum number of tokens to generate.
            - model: Pixtral-12b model instance.
            - processor: Pixtral-12b processor instance.
            - do_sample (bool): Whether to sample during generation.

    Returns:
        str: The generated response.
    """

    messages = response_kwargs["messages"]
    device = response_kwargs["device"]
    max_tokens = response_kwargs["max_tokens"]
    model = response_kwargs["model"]
    processor = response_kwargs["processor"]
    do_sample = response_kwargs.get("do_sample", False)

    phi_messages, image_paths = generate_phi_messages(messages)
    prompt = processor.apply_chat_template(phi_messages, tokenize=False, add_generation_prompt=True)

    processed_images = []
    for image in image_paths:
        if type(image) == str:
            processed_images.append(load_image(image))
        else:
            processed_images.append(image)

    image_paths = processed_images

    inputs = processor(prompt, image_paths, return_tensors="pt").to(device)

    generation_args = {
        "max_new_tokens": max_tokens,
        "temperature": 0.0,
        "do_sample": do_sample,
    }

    generate_ids = model.generate(**inputs,
                                  eos_token_id=processor.tokenizer.eos_token_id,
                                  **generation_args
                                  )
    # remove input tokens
    generate_ids = generate_ids[:, inputs['input_ids'].shape[1]:]
    response = processor.batch_decode(generate_ids, skip_special_tokens=True, clean_up_tokenization_spaces=False)[0]

    return response



"""
##### POINTS-1-5-Qwen-2-5-7B-Chat #####
"""

def generate_points_messages(messages: List[str]) -> Tuple[List, List]:
    """Generates Qwen-VL formatted messages and image inputs from a list of messages.

    Args:
        messages (List[Dict]): A list of message dictionaries containing user, assistant, and optionally images.

    Returns:
        Tuple[List, List]: A tuple containing:
            - A list of Qwen-VL formatted messages.
            - A list of image inputs extracted from the messages.
    """
    points_messages = []
    image_inputs = []

    for message in messages:
        message_dict = {'role': message['role'], 'content': []}

        if message['role'] == 'user':
            if 'image' in message:
                if isinstance(message['image'], str):
                    # Single image
                    message_dict['content'].append({"type": "image", "image": message['image']})
                    image_inputs.append(message['image'])
                elif isinstance(message['image'], list):
                    # Multiple images
                    for img in message['image']:
                        message_dict['content'].append({"type": "image", "image": img})
                        image_inputs.append(img)

                else:
                    raise ValueError("Invalid image type in message - should be str or list[str]")

            # Add user text
            if 'content' in message:
                message_dict['content'].append({"type": "text", "text": message['content']})

            points_messages.append(message_dict)

        elif message['role'] == 'assistant':
            # Add assistant response
            message_dict['content'].append({"type": "text", "text": message['content']})
            points_messages.append(message_dict)

        elif message['role'] == 'system':
            # Qwen-VL does not process system messages directly, so skip
            continue
        else:
            raise ValueError(f"Invalid role: {message['role']}. Expected 'user', 'assistant', or 'system'.")

    if points_messages and points_messages[-1]['role'] == 'user':
        content = points_messages[-1]['content']
        contains_image = any(item["type"] == "image" for item in content)

        if not contains_image:
            # Create a blank image and save it temporarily
            blank_image = Image.new("RGB", (128, 128), color="white")
            temp_path = "/tmp/blank_image.png"
            blank_image.save(temp_path)

            image_inputs.append(temp_path)
            points_messages[-1]['content'].append({"type": "image", "image": temp_path})

    return points_messages, image_inputs

def generate_points_prompt(messages: List[str], **prompt_kwargs) -> str:
    points_messages, _ = generate_points_messages(messages=messages)
    model = prompt_kwargs['model']
    img_processor = Qwen2VLImageProcessor.from_pretrained(prompt_kwargs['model_id'])
    prompt, _, _ = model.construct_prompt(points_messages, img_processor)
    return prompt

def generate_points_response(**response_kwargs) -> str:
    """Generates a response from the Qwen-vl model based on the provided messages and configuration.

    Args:
        **response_kwargs: A dictionary containing the following keys:
            - messages (List[str]): A list of message dictionaries.
            - device (str): The device to which the image tensors will be moved (e.g., 'cuda' or 'cpu').
            - max_tokens (int): The maximum number of tokens to generate.
            - model: The model instance used for generating responses.
            - processor: The processor instance used for processing images.

    Returns:
        str: The generated response from the LLAVA model.
    """

    messages = response_kwargs['messages']
    device = response_kwargs['device']
    max_tokens = response_kwargs['max_tokens']
    model = response_kwargs['model']
    processor = response_kwargs['processor']
    do_sample = response_kwargs['do_sample']
    model_id = response_kwargs['model_id']

    points_messages, image_paths = generate_points_messages(messages=messages)
    img_processor = Qwen2ImageProcessorForPOINTSV15.from_pretrained(model_id)


    # Process images

    generation_config = {
        'max_new_tokens': max_tokens,
        'temperature': 0.0,
        'top_p': 0.0,
        'do_sample': do_sample,
    }

    response = model.chat(
        points_messages,
        processor,
        img_processor,
        generation_config
    )

    return response

