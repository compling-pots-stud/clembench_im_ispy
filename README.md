# ISpy Game Setup

## Environment Setup

AI2Thor configuration is stored inside i_spy_final/env_backends/configs/environments.json

Starting scene, visibility distance, gridSize, fieldOfView, and Height/Width can be changed without breaking the game.

### Running Locally

In order to run locally, the platform argument should be removed from environments.json. Afterwards, the game can run without any additional setup. Upon starting the benchmark, an AI2Thor screen will render, and the game will start.

To install AI2Thor, run pip install ai2thor

### Running on a Linux Server

In order to run the game on a Linux server, you must first setup the environment. To do this, run setup_ai2.sh script, which will install the required linux packages, and initiate an 800x600 virtual display. Note that we need to initiate the virtual displays every time the environment is restarted. 

Additionally, the add "platform": "CloudRendering" to the environments.json configuration file. This will enable running AI2Thor headless.


## Folder structure

Inside i_spy_final/env_backends you can find the code used to integrate AI2Thor and other potential environment into the game. 

On every turn, all relevant metadata will be stored inside the metadata folder inside a json file.
Moreover, the frames from each turn are stored inside the images folder.

Both metadata and images folders maintain the following structure: model/experiment/instance

### Updates
(February 2024): We have updated the framework code. If you have written games using the initial release version, see [this guide](docs/howto_update_to_v1.md) on how to update your game.

# clembench: A Framework for the Systematic Evaluation of Chat-Optimized Language Models as Conversational Agents

The cLLM (chat-optimized Large Language Model, "clem") framework tests such models' ability to engage in games – rule-constituted activities played using language.
The framework is a systematic way of probing for the situated language understanding of language using agents.

This repository contains the code for setting up the framework and implements a number of games that are further discussed in 

> Chalamalasetti, K., Götze, J., Hakimov, S., Madureira, B., Sadler, P., & Schlangen, D. (2023). clembench: Using Game Play to Evaluate Chat-Optimized Language Models as Conversational Agents (arXiv:2305.13455). arXiv. https://doi.org/10.48550/arXiv.2305.13455

### Evaluation Results

On the [main project website](https://clembench.github.io) , under [leaderboard](https://clembench.github.io/leaderboard.html).

### Game details

- A Simple Word Game: [taboo](docs/taboo.md)
- A Word-Guessing Game Based on Clues: [wordle](docs/wordle.md)
- Drawing Instruction Giving and Following: [image](docs/image.md)
- An ASCII Picture Reference Game: [reference](docs/reference.md)
- Scorekeeping: [private and shared](docs/privateshared.md)

## Using the benchmark

This repository is tested on `Python 3.8+`

We welcome you to contribute to or extend the benchmark with your own games and models. 
Please simply open a pull request. You can find more information on how to use the benchmark in the links below.

- [How to run the benchmark and evaluation locally](docs/howto_run_benchmark.md)
- [How to run the benchmark, update leaderboard workflow](docs/howto_benchmark_workflow.md)
- [How to add a new model](docs/howto_add_models.md)
- [How to add and run your own game](docs/howto_add_games.md)
- [How to integrate with Slurk](docs/howto_slurk.md)
