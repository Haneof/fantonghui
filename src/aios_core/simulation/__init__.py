from .headless_life_driver import HeadlessLifeDriver, RunReport, SimConfig, load_token_policy
from .life_spectrum_question_engine import SevenDimensionalQuestionEngine

__all__ = [
    'HeadlessLifeDriver',
    'RunReport',
    'SimConfig',
    'load_token_policy',
    'SevenDimensionalQuestionEngine',
    'CleaningQuestionGenerator',
    'HighEntropyQuestionGenerator',
    'QuestionGenerator',
    'SevenDimensionQuestionGenerator',
    'generate_cleaning_dataset',
]


def __getattr__(name: str):
    """Load the local 7D examiner aliases only when they are requested."""

    if name in {
        'CleaningQuestionGenerator',
        'HighEntropyQuestionGenerator',
        'QuestionGenerator',
        'SevenDimensionQuestionGenerator',
        'generate_cleaning_dataset',
    }:
        from .question_generator import (
            CleaningQuestionGenerator,
            HighEntropyQuestionGenerator,
            QuestionGenerator,
            SevenDimensionQuestionGenerator,
            generate_cleaning_dataset,
        )
        return {
            'CleaningQuestionGenerator': CleaningQuestionGenerator,
            'HighEntropyQuestionGenerator': HighEntropyQuestionGenerator,
            'QuestionGenerator': QuestionGenerator,
            'SevenDimensionQuestionGenerator': SevenDimensionQuestionGenerator,
            'generate_cleaning_dataset': generate_cleaning_dataset,
        }[name]
    raise AttributeError(name)
