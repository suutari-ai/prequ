import os
from textwrap import dedent
from six.moves.urllib.request import pathname2url
import subprocess
import sys
import mock

from click.testing import CliRunner

import pytest
from piptools.scripts.compile import cli
from piptools.scripts.sync import cli as sync_cli


@pytest.yield_fixture
def pip_conf(tmpdir):
    test_conf = dedent("""\
        [global]
        index-url = http://example.com
        trusted-host = example.com
    """)

    pip_conf_file = 'pip.conf' if os.name != 'nt' else 'pip.ini'
    path = (tmpdir / pip_conf_file).strpath

    with open(path, 'w') as f:
        f.write(test_conf)

    old_value = os.environ.get('PIP_CONFIG_FILE')
    try:
        os.environ['PIP_CONFIG_FILE'] = path
        yield path
    finally:
        if old_value is not None:
            os.environ['PIP_CONFIG_FILE'] = old_value
        else:
            del os.environ['PIP_CONFIG_FILE']
        os.remove(path)


def test_default_pip_conf_read(pip_conf):

    assert os.path.exists(pip_conf)

    runner = CliRunner()
    with runner.isolated_filesystem():
        # preconditions
        with open('requirements.in', 'w'):
            pass
        out = runner.invoke(cli, ['-v'])

        # check that we have our index-url as specified in pip.conf
        assert 'Using indexes:\n  http://example.com' in out.output
        assert '--index-url http://example.com' in out.output


def test_command_line_overrides_pip_conf(pip_conf):

    assert os.path.exists(pip_conf)

    runner = CliRunner()
    with runner.isolated_filesystem():
        # preconditions
        with open('requirements.in', 'w'):
            pass
        out = runner.invoke(cli, ['-v', '-i', 'http://override.com'])

        # check that we have our index-url as specified in pip.conf
        assert 'Using indexes:\n  http://override.com' in out.output


def test_command_line_setuptools_read(pip_conf):

    runner = CliRunner()
    with runner.isolated_filesystem():
        package = open('setup.py', 'w')
        package.write(dedent("""\
            from setuptools import setup
            setup(install_requires=[])
        """))
        package.close()
        out = runner.invoke(cli)

        # check that pip-compile generated a configuration
        assert 'This file is autogenerated by pip-compile' in out.output


def test_find_links_option(pip_conf):

    assert os.path.exists(pip_conf)

    runner = CliRunner()
    with runner.isolated_filesystem():
        with open('requirements.in', 'w'):
            pass
        out = runner.invoke(cli, ['-v', '-f', './libs1', '-f', './libs2'])

        # Check that find-links has been passed to pip
        assert 'Configuration:\n  -f ./libs1\n  -f ./libs2' in out.output


def test_extra_index_option(pip_conf):

    assert os.path.exists(pip_conf)

    runner = CliRunner()
    with runner.isolated_filesystem():
        with open('requirements.in', 'w'):
            pass
        out = runner.invoke(cli, ['-v',
                                  '--extra-index-url', 'http://extraindex1.com',
                                  '--extra-index-url', 'http://extraindex2.com'])
        assert ('Using indexes:\n'
                '  http://example.com\n'
                '  http://extraindex1.com\n'
                '  http://extraindex2.com' in out.output)
        assert ('--index-url http://example.com\n'
                '--extra-index-url http://extraindex1.com\n'
                '--extra-index-url http://extraindex2.com' in out.output)


def test_trusted_host(pip_conf):
    assert os.path.exists(pip_conf)

    runner = CliRunner()
    with runner.isolated_filesystem():
        with open('requirements.in', 'w'):
            pass
        out = runner.invoke(cli, ['-v',
                                  '--trusted-host', 'example.com',
                                  '--trusted-host', 'example2.com'])
        assert ('--trusted-host example.com\n'
                '--trusted-host example2.com\n' in out.output)


def test_trusted_host_no_emit(pip_conf):
    assert os.path.exists(pip_conf)

    runner = CliRunner()
    with runner.isolated_filesystem():
        with open('requirements.in', 'w'):
            pass
        out = runner.invoke(cli, ['-v',
                                  '--trusted-host', 'example.com',
                                  '--no-emit-trusted-host'])
        assert '--trusted-host example.com' not in out.output
        assert '--no-emit-trusted-host' in out.output


def test_realistic_complex_sub_dependencies(tmpdir):

    # make a temporary wheel of a fake package
    subprocess.check_output(['pip', 'wheel',
                             '--no-deps',
                             '-w', str(tmpdir),
                             os.path.join('.', 'tests', 'fixtures', 'fake_package', '.')])

    runner = CliRunner()
    with runner.isolated_filesystem():
        with open('requirements.in', 'w') as req_in:
            req_in.write('fake_with_deps')  # require fake package

        out = runner.invoke(cli, ['-v',
                                  '-n', '--rebuild',
                                  '-f', str(tmpdir)])

        assert out.exit_code == 0


def _invoke(command):
    """Invoke sub-process."""
    try:
        output = subprocess.check_output(
            command,
            stderr=subprocess.STDOUT,
        )
        status = 0
    except subprocess.CalledProcessError as error:
        output = error.output
        status = error.returncode

    return status, output


def test_run_as_module_compile(tmpdir):
    """piptools can be run as ``python -m piptools ...``."""

    status, output = _invoke([
        sys.executable, '-m', 'piptools', 'compile', '--help',
    ])

    # Should have run pip-compile successfully.
    output = output.decode('utf-8')
    assert output.startswith('Usage:')
    assert 'Compiles requirements.txt from requirements.in' in output
    assert status == 0


def test_run_as_module_sync():
    """piptools can be run as ``python -m piptools ...``."""

    status, output = _invoke([
        sys.executable, '-m', 'piptools', 'sync', '--help',
    ])

    # Should have run pip-compile successfully.
    output = output.decode('utf-8')
    assert output.startswith('Usage:')
    assert 'Synchronize virtual environment with' in output
    assert status == 0


def test_sync_quiet(tmpdir):
    """sync command can be run with `--quiet` or `-q` flag."""

    runner = CliRunner()
    with runner.isolated_filesystem():
        with open('requirements.txt', 'w') as req_in:
            req_in.write('six==1.10.0')

        with mock.patch('piptools.sync.check_call') as check_call:
            out = runner.invoke(sync_cli, ['-q'])
            assert out.output == ''
            assert out.exit_code == 0
            # for every call to pip ensure the `-q` flag is set
            for call in check_call.call_args_list:
                assert '-q' in call[0][0]


@pytest.mark.parametrize('option_name', [
    'find-links', 'f', 'no-index', 'index-url', 'i', 'extra-index-url'])
def test_sync_uses_opts_from_txt_file(option_name):
    """sync command uses pip options from the txt file."""
    (opt_in_txt_file, pip_opt) = {
        'find-links': ('--find-links ./pkg-dir', '-f ./pkg-dir'),
        'f': ('-f ./pkg-dir', '-f ./pkg-dir'),
        'no-index': ('--no-index', '--no-index'),
        'index-url': ('--index-url http://index-url', '-i http://index-url'),
        'i': ('-i http://index.localhost', '-i http://index.localhost'),
        'extra-index-url': (
            '--extra-index-url http://extra-index.localhost',
            '--extra-index-url http://extra-index.localhost'),
    }[option_name]
    runner = CliRunner()
    with runner.isolated_filesystem():
        with open('requirements.txt', 'w') as req_txt:
            req_txt.write('{}\n'.format(opt_in_txt_file))
            req_txt.write('foobar==0.42\n')

        with mock.patch('piptools.sync.check_call') as check_call:
            run_result = runner.invoke(sync_cli, ['-q'])
            assert run_result.output == ''
            assert run_result.exit_code == 0
            number_of_install_calls = 0
            for (call_args, _call_kwargs) in check_call.call_args_list:
                cmd = ' '.join(call_args[0])
                if cmd.startswith('pip install'):
                    assert pip_opt in cmd
                    number_of_install_calls += 1
            assert number_of_install_calls == 1


def test_editable_package(tmpdir):
    """ piptools can compile an editable """
    fake_package_dir = os.path.join(os.path.split(__file__)[0], 'fixtures', 'small_fake_package')
    fake_package_dir = 'file:' + pathname2url(fake_package_dir)
    runner = CliRunner()
    with runner.isolated_filesystem():
        with open('requirements.in', 'w') as req_in:
            req_in.write('-e ' + fake_package_dir)  # require editable fake package

        out = runner.invoke(cli, ['-n'])

        assert out.exit_code == 0
        assert fake_package_dir in out.output
        assert 'six==1.10.0' in out.output


def test_editable_package_vcs(tmpdir):
    vcs_package = (
        'git+git://github.com/pytest-dev/pytest-django'
        '@21492afc88a19d4ca01cd0ac392a5325b14f95c7'
        '#egg=pytest-django'
    )
    runner = CliRunner()
    with runner.isolated_filesystem():
        with open('requirements.in', 'w') as req_in:
            req_in.write('-e ' + vcs_package)
        out = runner.invoke(cli, ['-n',
                                  '--rebuild'])
        print(out.output)
        assert out.exit_code == 0
        assert vcs_package in out.output
        assert 'pytest' in out.output  # dependency of pytest-django


def test_locally_available_editable_package_is_not_archived_in_cache_dir(tmpdir):
    """ piptools will not create an archive for a locally available editable requirement """
    cache_dir = tmpdir.mkdir('cache_dir')

    fake_package_dir = os.path.join(os.path.split(__file__)[0], 'fixtures', 'small_fake_package')
    fake_package_dir = 'file:' + pathname2url(fake_package_dir)

    with mock.patch('piptools.repositories.pypi.CACHE_DIR', new=str(cache_dir)):
        runner = CliRunner()
        with runner.isolated_filesystem():
            with open('requirements.in', 'w') as req_in:
                req_in.write('-e ' + fake_package_dir)  # require editable fake package

            out = runner.invoke(cli, ['-n'])

            assert out.exit_code == 0
            assert fake_package_dir in out.output
            assert 'six==1.10.0' in out.output

    # we should not find any archived file in {cache_dir}/pkgs
    assert not os.listdir(os.path.join(str(cache_dir), 'pkgs'))


def test_input_file_without_extension(tmpdir):
    """
    piptools can compile a file without an extension,
    and add .txt as the defaut output file extension.
    """
    runner = CliRunner()
    with runner.isolated_filesystem():
        with open('requirements', 'w') as req_in:
            req_in.write('six==1.10.0')

        out = runner.invoke(cli, ['-n', 'requirements'])

        assert out.exit_code == 0
        assert '--output-file requirements.txt' in out.output
        assert 'six==1.10.0' in out.output


def test_upgrade_packages_option(tmpdir):
    """
    piptools respects --upgrade-package/-P inline list.
    """
    fake_package_dir = os.path.join(os.path.split(__file__)[0], 'fixtures', 'minimal_wheels')
    runner = CliRunner()
    with runner.isolated_filesystem():
        with open('requirements.in', 'w') as req_in:
            req_in.write('small-fake-a\nsmall-fake-b')
        with open('requirements.txt', 'w') as req_in:
            req_in.write('small-fake-a==0.1\nsmall-fake-b==0.1')

        out = runner.invoke(cli, [
            '-P', 'small_fake_b',
            '-f', fake_package_dir,
        ])

        assert out.exit_code == 0
        assert 'small-fake-a==0.1' in out.output
        assert 'small-fake-b==0.2' in out.output


def test_generate_hashes_with_editable():
    small_fake_package_dir = os.path.join(
        os.path.split(__file__)[0], 'fixtures', 'small_fake_package')
    small_fake_package_url = 'file:' + pathname2url(small_fake_package_dir)
    runner = CliRunner()
    with runner.isolated_filesystem():
        with open('requirements.in', 'w') as fp:
            fp.write('-e {}\n'.format(small_fake_package_url))
            fp.write('pytz==2017.2\n')
        out = runner.invoke(cli, ['--generate-hashes'])
    expected = (
        '#\n'
        '# This file is autogenerated by pip-compile\n'
        '# To update, run:\n'
        '#\n'
        '#    pip-compile --generate-hashes --output-file requirements.txt requirements.in\n'
        '#\n'
        '-e {}\n'
        'pytz==2017.2 \\\n'
        '    --hash=sha256:d1d6729c85acea5423671382868627129432fba9a89ecbb248d8d1c7a9f01c67 \\\n'
        '    --hash=sha256:f5c056e8f62d45ba8215e5cb8f50dfccb198b4b9fbea8500674f3443e4689589\n'
    ).format(small_fake_package_url)
    assert out.exit_code == 0
    assert expected in out.output
