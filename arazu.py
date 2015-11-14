#!/usr/bin/env python
"""
Arazu

Provides single-command management of the build/deploy cycle for projects that
generate an output folder of some kind (originally for static sites but can be
for anything that fits the model).

Arazu is not a build system - you should already have a system that builds your
finished output. Instead, arazu is simply a helper tool that runs your build
command, commits the output into a separate repository and/or branch, and
pushes to it with a helpful commit message. The only goal is to remove the
manual step of deploying, particularly for things where the deployable product
lives in a repository but the source should not be included with it (like
static sites).

Assumes the code lives in git and the project can be deployed via git push.
Supports things like hosting the code in one repository (maybe local, private,
or on-prem) and deploying it using a different one (github pages, heroku, ci,
etc).

Quick Start:
    Create an arazu.yaml file with your repository info and build commands
    -- use `arazu init` to create a starting template

    Once you set up your config, just run
    `arazu deploy`


Full Lifecycle:
  -- your project already works and builds to a single output folder --

  `arazu deploy`
    - arazu bails if you have local changes - stash them to continue
    - arazu runs your configured build command
    - arazu creates a new deploy folder
    - arazu clones your deploy repository to the deploy folder and checks
    out your deploy branch
    - arazu copies your configured build output folder to the deploy folder
    - arazu adds everything (using `git add .`) and commits it with a simple
    commit message included the current date/time and the commit hash from
    the source repository.
    - arazu pushes the commit to the deploy branch of your deploy repo
"""

import argparse
import os
import sys
import logging
import yaml
import subprocess
import shutil
import datetime
import tempfile

DEFAULT_CONFIG_PATH = 'arazu.yaml'
COMMIT_MESSAGE_FILEPATH = '.arazu_commit_message'
CONFIG_TEMPLATE_RAW = """# Arazu Config - check this in to source control

# where the source code lives
source-repo: "fill this in - no branch name"
source-branch: master

# where the deploy code lives
deploy-repo: "fill this in - no branch name"
# if github, use master for organization sites, gh-pages for project
deploy-branch: gh-pages

# build command - this gets called to make your build
build-command: "fill this in"

# folder with build output - this gets commited into the deploy repo
build-folder: "fill this in"

# format for commit message - can include {date} and {sha}
commit-template: |
  Deploy {date}

  SHA: {sha}
"""


config_template = yaml.load(CONFIG_TEMPLATE_RAW)


class AbortError(Exception):
    pass


def abort(message):
    logging.error('ERROR - ' + message)
    raise AbortError(message)


def validate_not_default(config, fields):
    for field in fields:
        if config[field] == config_template[field]:
            abort('invalid config - you must set the %s value' % field)


def call_or_fail(command):
    proc = subprocess.call(command, shell=True)
    if proc != 0:
        sys.exit(1)
    return proc


class Arazu(object):

    def __init__(self, args):
        self.args = args

    def create_config(self):
        config_file_path = DEFAULT_CONFIG_PATH
        if os.path.exists(config_file_path):
            abort(
                'config file "%s" already exists - delete it to continue' % (
                    config_file_path,
                )
            )

        try:
            config_file = open(config_file_path, 'w')
            config_file.write(CONFIG_TEMPLATE_RAW)
        except:
            abort('failed to write config file "%s"' % config_file_path)
        finally:
            config_file.close()

        if not self.args.quiet:
            print('new config template at "%s"!', config_file_path)
            print('fill it out and run `arazu build`')

    def parse_config(self, config_file_path):
        # look for config file
        if not os.path.exists(config_file_path):
            abort('could not find config file "%s"' % config_file_path)

        # try to open config file
        try:
            config_file = open(config_file_path, 'r')
        except:
            abort('failed to open config file "%s"' % config_file_path)

        # try to parse config file
        config = None
        try:
            config = yaml.load(config_file)
        except:
            config_file.close()
            abort('failed to parse config file "%s"' % config_file_path)

        # validate config
        validate_not_default(
            config,
            [
                'build-command',
                'build-folder',
                'source-repo',
                'deploy-repo',
            ]
        )

        # save config
        self.config = config

    def deploy(self):
        self.parse_config(self.args.config)

        # look for local changes
        logging.info('checking for local changes')
        changes = subprocess.call(
            'git diff --no-ext-diff --quiet --exit-code',
            shell=True
        )

        if changes:
            abort(
                'arazu cannot deploy with local changes '
                + '- commit everything and try again'
                )

        # build correct commit message
        logging.info('generating commit message')
        p = subprocess.Popen(
            ['git', 'rev-parse', 'HEAD'],
            # stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            # bufsize=1,
        )
        latest_commit_sha = p.stdout.readline().decode().strip()

        # run build command
        build_command = self.config['build-command']
        logging.info('running build command "%s"' % build_command)
        if build_command not in ['', None]:
            call_or_fail(build_command)

        # save current path
        original_path = os.path.abspath(os.curdir)

        # create and change to deploy folder
        deploy_folder = tempfile.mkdtemp(prefix='arazu_deploy')
        logging.debug(
            'creating and changing to deploy folder %s',
            deploy_folder
        )
        os.chdir(deploy_folder)

        # wrap in try so deploy_folder gets cleaned up no matter what
        try:
            # check out repository
            logging.info('setting up repository')
            call_or_fail('git init')
            logging.info('adding deploy remote')
            call_or_fail(
                'git remote add deploy %s' % self.config['deploy-repo']
            )

            # change to correct branch
            deploy_branch = self.config['deploy-branch']
            logging.info('setting branch "%s"' % deploy_branch)
            call_or_fail('git fetch deploy')

            # use existing branch if it exists
            result = subprocess.call(
                'git checkout %s' % deploy_branch,
                shell=True
            )

            if result != 0:
                logging.info('creating deploy branch "%s"', deploy_branch)
                call_or_fail('git checkout -b %s' % deploy_branch)

            # copy source folder onto deploy folder
            build_folder = os.path.join(
                original_path,
                self.config['build-folder']
            )
            logging.info(
                'copying build output {build_folder} to deploy folder'.format(
                    build_folder=build_folder
                )
            )
            build_glob = os.path.join(build_folder, '*')
            call_or_fail(
                'cp -r {build_glob} .'.format(
                    build_glob=build_glob
                )
            )

            commit_message = self.config['commit-template'].format(
                sha=latest_commit_sha,
                date=str(datetime.datetime.now())
            )
            commit_message_filepath = COMMIT_MESSAGE_FILEPATH
            if self.args.dry_run and not self.args.quiet:
                print("Dry Run - Commit Message: %s" % commit_message)
            f = open(commit_message_filepath, 'w')
            f.write(commit_message)
            f.close()

            # stage and commit files
            logging.info('adding changes to deploy repository')
            call_or_fail('git add .')
            call_or_fail('git reset %s' % commit_message_filepath)
            logging.info('creating new deploy commit')
            call_or_fail('git commit -F %s' % commit_message_filepath)

            if self.args.dry_run:
                if not self.args.quiet:
                    print('Dry Run Complete!')
                    print('Deploy folder is: %s"' % deploy_folder)
                    print('Delete the deploy folder when finished')
            else:
                logging.info('pushing latest build')
                call_or_fail('git push deploy %s' % deploy_branch)

                # delete commit message
                logging.info('deleting temp commit message file')
                os.unlink(commit_message_filepath)

            if not self.args.quiet:
                print('Deploy complete for commit  %s' % latest_commit_sha)

        except AbortError:
            logging.error(
                'Something went wrong and arazu aborted your deploy.'
            )

        finally:
            try:
                logging.info(
                    'deleting temporary deploy folder %s' % deploy_folder
                )
                shutil.rmtree(deploy_folder)
            # open except - sorry :(
            except:
                logging.error(
                    'Failed to delete deploy folder. Please delete it by hand.'
                )
                logging.error(deploy_folder)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        'command',
        help='arazu command to run',
        choices=['init', 'deploy']
    )
    parser.add_argument(
        '--config',
        default=DEFAULT_CONFIG_PATH,
        help='path to the config file - defaults to "%s"' % DEFAULT_CONFIG_PATH
    )
    parser.add_argument(
        '--dry-run',
        dest='dry_run',
        action='store_true',
        default=False,
        help=(
            'use --dry-run to run everything except the final commit. '
            + 'you will need to manually delete the deploy folder after '
            + 'every dry-run.'
        )
    )
    parser.add_argument(
        '-q', '--quiet',
        dest='quiet',
        action='store_true',
        default=False,
        help='supress print output'
    )

    args = parser.parse_args()

    level = logging.WARNING if args.quiet else logging.INFO
    logging.basicConfig(level=level, format='%(message)s')

    arazu = Arazu(args)

    if args.command == 'deploy':
        arazu.deploy()
    elif args.command == 'init':
        arazu.create_config()
    else:
        parser.print_usage()


if __name__ == '__main__':
    main()
