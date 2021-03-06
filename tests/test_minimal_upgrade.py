import pytest

from prequ.repositories import LocalRequirementsRepository
from prequ.utils import key_from_ireq


@pytest.mark.parametrize(
    ('input', 'pins', 'expected'),

    ((tup) for tup in [

        # Add Flask to an existing requirements.in, using --no-upgrade
        (['flask', 'jinja2', 'werkzeug'],
         [
            # The requirements.txt from a previous round
            'jinja2==2.7.3',
            'markupsafe==0.23',
            'werkzeug==0.6'],
         [
            # Add flask and upgrade werkzeug from incompatible 0.6
            'flask==0.10.1',
            'itsdangerous==0.24',
            'werkzeug==0.10.4',
            # Other requirements are unchanged from the original requirements.txt
            'jinja2==2.7.3',
            'markupsafe==0.23']
         ),
    ])
)
def test_no_upgrades(base_resolver, repository, from_line, input, pins, expected):
    input = [from_line(line) for line in input]
    existing_pins = dict()
    for line in pins:
        ireq = from_line(line)
        existing_pins[key_from_ireq(ireq)] = ireq
    local_repository = LocalRequirementsRepository(existing_pins, repository)
    output = base_resolver(input, prereleases=False, repository=local_repository).resolve()
    output = {str(line) for line in output}
    assert output == {str(line) for line in expected}
