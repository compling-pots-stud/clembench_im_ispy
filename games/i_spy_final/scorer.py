import sys
from typing import Dict

import numpy as np
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent.parent))
from clemgame.clemgame import GameScorer
from clembench.clemgame.metrics import *


GAME_NAME = 'i_spy_final'


class ISpyScorer(GameScorer):

    def __init__(self, experiment: dict, game_instance: dict):
        super().__init__(GAME_NAME, experiment, game_instance)

    def compute_scores(self, episode_interactions: Dict) -> None:
        learner_request_count = self.compute_turn_scores(episode_interactions)
        self.compute_episode_scores(episode_interactions, learner_request_count)

    def compute_turn_scores(self, episode_interactions):
        learner_request_count = 0

        for idx, turn in enumerate(episode_interactions['turns']):
            turn_score_dict = {
                'learner_parsing_error_count': 0,
                'teacher_parsing_error_count': 0,
                'parsing_error_count': 0,
                'learner_move': 0,
                'learner_guess': 0,
                'learner_question': 0,
                'teacher_success': 0,
                'teacher_answer': 0,
                'teacher_incorrect': 0,
                'request_count': 0,
                'parsed_request_count': 0,
                'reprompt_attempts': 0,
                'learner_reprompt_attempt': 0,
                'teacher_reprompt_attempt': 0,
                'aborted': 0,
                'success': 0,
                'lost': 0,
                'object_in_frame': 0,
                'learner_request_count' : 0
            }

            for event in turn:
                action = event['action']

                if action['type'] == 'learner_parsing_error':
                    turn_score_dict['learner_parsing_error_count'] += 1
                    turn_score_dict['parsing_error_count'] += 1
                    turn_score_dict['request_count'] += 1

                elif action['type'] == 'teacher_parsing_error':
                    turn_score_dict['teacher_parsing_error_count'] += 1
                    turn_score_dict['parsing_error_count'] += 1
                    turn_score_dict['request_count'] += 1

                elif action['type'] == 'valid format':
                    turn_score_dict['request_count'] += 1
                    turn_score_dict['parsed_request_count'] += 1

                elif action['type'] == 'reprompt_attempt':
                    turn_score_dict['request_count'] += 1
                    turn_score_dict['reprompt_attempts'] += 1

                    if action['content'] == 'Learner':
                        turn_score_dict['learner_reprompt_attempt'] += 1

                    else:
                        turn_score_dict['teacher_reprompt_attempt'] += 1

                elif action['type'] == 'object_status':
                    if action['content'] == 'visible':
                        turn_score_dict['object_in_frame'] += 1

                elif action['type'] == 'record_move':
                    turn_score_dict['learner_move'] += 1

                elif action['type'] == 'record_question':
                    turn_score_dict['learner_question'] += 1
                    turn_score_dict['learner_request_count'] += 1

                elif action['type'] == 'record_guess':
                    turn_score_dict['learner_guess'] += 1
                    turn_score_dict['learner_request_count'] += 1

                elif action['type'] == 'record_success':
                    turn_score_dict['teacher_success'] += 1

                elif action['type'] == 'record_answer':
                    turn_score_dict['teacher_answer'] += 1

                elif action['type'] == 'record_incorrect':
                    turn_score_dict['teacher_incorrect'] += 1


                elif action['type'] == 'success':
                    turn_score_dict['success'] += 1


                elif action['type'] == 'max turns reached':
                    turn_score_dict['lost'] += 1


                elif action['type'] == 'max reprompts reached':
                    turn_score_dict['aborted'] += 1

            learner_request_count += turn_score_dict['learner_request_count']

            self.log_turn_score(idx, METRIC_ABORTED, turn_score_dict['aborted'])
            self.log_turn_score(idx, METRIC_SUCCESS, turn_score_dict['success'])
            self.log_turn_score(idx, METRIC_LOSE, turn_score_dict['lost'])
            self.log_turn_score(idx, METRIC_REQUEST_COUNT, turn_score_dict['request_count'])
            self.log_turn_score(idx, METRIC_REQUEST_COUNT_PARSED, turn_score_dict['parsed_request_count'])
            self.log_turn_score(idx, METRIC_REQUEST_COUNT_VIOLATED, turn_score_dict['parsing_error_count'])
            # print(f"parsed: {turn_score_dict['parsed_request_count']}, total: {turn_score_dict['request_count']}")
            # print()
            self.log_turn_score(idx, METRIC_REQUEST_SUCCESS, turn_score_dict['parsed_request_count']/turn_score_dict[
                'request_count'] if turn_score_dict['request_count'] > 0 else None)

            self.log_turn_score(idx, 'Learner Parsing Error Count', turn_score_dict['learner_parsing_error_count'])
            self.log_turn_score(idx, 'Teacher Parsing Error Count', turn_score_dict['teacher_parsing_error_count'])
            self.log_turn_score(idx, 'Learner Request Count', turn_score_dict['learner_request_count'])
            self.log_turn_score(idx, 'Learner Move', turn_score_dict['learner_move'])
            self.log_turn_score(idx, 'Learner Guess', turn_score_dict['learner_guess'])
            self.log_turn_score(idx, 'Learner Question', turn_score_dict['learner_question'])
            self.log_turn_score(idx, 'Teacher Answer', turn_score_dict['teacher_answer'])
            self.log_turn_score(idx, 'Teacher Success Call', turn_score_dict['teacher_success'])
            self.log_turn_score(idx, 'Teacher Incorrect Guess Call', turn_score_dict['teacher_incorrect'])
            self.log_turn_score(idx, 'Object Visible', turn_score_dict['object_in_frame'])
            self.log_turn_score(idx, 'Reprompt Attempts', turn_score_dict['reprompt_attempts'])
            self.log_turn_score(idx, 'Reprompt Attempts Learner', turn_score_dict['learner_reprompt_attempt'])
            self.log_turn_score(idx, 'Reprompt Attempts Teacher', turn_score_dict['teacher_reprompt_attempt'])

        return learner_request_count

    def compute_episode_scores(self, episode_interactions: Dict, learner_request_count: int):

        is_aborted = episode_interactions['Aborted']
        is_success = episode_interactions['Success']
        is_lost = episode_interactions['Lose']

        if is_aborted:
            self.log_episode_score(METRIC_ABORTED, 1)
            self.log_episode_score(METRIC_LOSE, 0)
            self.log_episode_score(METRIC_SUCCESS, 0)

        elif is_success:
            self.log_episode_score(METRIC_ABORTED, 0)
            self.log_episode_score(METRIC_LOSE, 0)
            self.log_episode_score(METRIC_SUCCESS, 1)

        elif is_lost:
            self.log_episode_score(METRIC_ABORTED, 0)
            self.log_episode_score(METRIC_LOSE, 1)
            self.log_episode_score(METRIC_SUCCESS, 0)

        self.log_episode_score(METRIC_REQUEST_COUNT, episode_interactions['Request Count'])
        self.log_episode_score(METRIC_REQUEST_COUNT_PARSED, episode_interactions['Parsed Request Count'])
        self.log_episode_score(METRIC_REQUEST_COUNT_VIOLATED, episode_interactions['Request Count'] - episode_interactions['Parsed Request Count'])
        self.log_episode_score(METRIC_REQUEST_SUCCESS,
                               episode_interactions['Parsed Request Count']/episode_interactions['Request Count'] if
                               episode_interactions['Request Count'] > 0 else None)

        self.log_episode_score('Learner Error Count', episode_interactions['learner_error_count'])
        self.log_episode_score('Teacher Error Count', episode_interactions['teacher_error_count'])
        self.log_episode_score('Learner Reprompt Count', episode_interactions['learner_reprompts'])
        self.log_episode_score('Teacher Reprompt Count', episode_interactions['teacher_reprompts'])

        self.log_episode_score('Learner Move Error Count', episode_interactions['move_error_count'])
        self.log_episode_score('Learner Guess Error Count', episode_interactions['guess_error_count'])
        self.log_episode_score('Learner Guess Attempt Count', episode_interactions['guess_attempt_count'])
        self.log_episode_score('Learner Guess Success Count', 1 if is_success else 0)
        self.log_episode_score('Learner Move Error Percentage',
                               episode_interactions['move_error_count']/episode_interactions['learner_error_count']
                               if episode_interactions['learner_error_count'] > 0 else None)

        self.log_episode_score('Learner Guess Error Percentage',
                               episode_interactions['guess_error_count']/episode_interactions['learner_error_count']
                               if episode_interactions['learner_error_count'] > 0 else None)

        learner_guess_accuracy = 1/episode_interactions['guess_attempt_count'] if is_success else 0
        turn_efficiency = 1 - (episode_interactions['learner_error_count'] / learner_request_count) if (
            learner_request_count) > 0 else 0


        self.log_episode_score('Learner Guess Accuracy', learner_guess_accuracy)
        self.log_episode_score('Learner Turn Efficiency', turn_efficiency)

        # max score is 1
        # learner guess acc is 0 if object isn't identified
        # points deducted in turn_efficiency for every parsing error made by the learner.
        # main score evaluates the ability to guess + instruction following ability.
        main_score = ((learner_guess_accuracy + turn_efficiency) / 2)*100
        self.log_episode_score(BENCH_SCORE, main_score)


if __name__ == '__main__':
    from clemgame import benchmark
    from scripts.cli import read_model_specs

    gen_args: dict[str: str] = {"temperature": 0.0, "max_tokens": 400}
    instances_name: str = "instances"
    results_dir: str = "results"
    model_specs: list[str] = ["gpt-4o-2024-08-06", "gpt-4o-mini"]

    benchmark.score(
        game_name=GAME_NAME,
    )

