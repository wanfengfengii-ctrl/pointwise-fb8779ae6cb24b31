from dataclasses import dataclass

from survey.layout import PortRef, SurveyLayout


@dataclass(frozen=True)
class ReviewRequest:
    probe_a: str
    probe_b: str
    start: PortRef
    finish: PortRef
    threshold: int


def validate_request(layout: SurveyLayout, probe_a: str, probe_b: str, threshold: int) -> ReviewRequest:
    if type(threshold) is not int or not 0 <= threshold <= 100:
        raise ValueError('threshold must be an integer from 0 to 100')
    try:
        start, finish = layout.probe(probe_a), layout.probe(probe_b)
    except KeyError as error:
        raise ValueError('probe is not registered in the survey') from error
    return ReviewRequest(probe_a, probe_b, start, finish, threshold)
