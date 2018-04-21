'''
A fabric file to automate creation of a special distribution of
xbmcswift2 for XBMC. This distribution doesn't include docs and tests.
It has a slightly different folder structure and contains some XBMC
specific files.

Usage:
    # Create a new release for Dharma
    $ fab release:dharma,prepare
    # Edit the changelog.txt in the temp directory and `git add` it
    $ fab release:dharma,perform
'''
import tempfile
import shutil
import os
from xml.etree import ElementTree as ET
import subprocess
import xam
from fabric.api import *
import fabric.colors as colors


EDITOR = 'nano'
REPO_DIR = 'xbmcswift2-xbmc-dist'
REPO_URL = 'git@github.com:predakanga/xbmcswift2-xbmc-dist.git'
REPO_PUBLIC_URL = 'git://github.com/predakanga/xbmcswift2-xbmc-dist.git'
BRANCHES = {
    # <xbmc_version>: <git_branch>
    'DHARMA': 'dharma',
    'EDEN': 'eden',
    'FRODO': 'frodo',
    'LEIA': 'master',
}


def log(msg, important=False):
    if important:
        puts(colors.green(msg))
    else:
        puts(colors.yellow(msg))


class GitRepo(object):
    def __init__(self, path=None, remote_url=None):
        self.path = path
        self.remote_url = remote_url

    def clone(self, parent_dir):
        with lcd(parent_dir):
            local('git clone %s' % self.remote_url)

    def stage_all(self):
        with lcd(self.path):
            local('git add -A')

    def get_head_hash(self):
        with lcd(self.path):
            return local('git log | head -1 | cut -f2 -d" "', capture=True)

    def checkout_remote_branch(self, branch):
        with lcd(self.path):
            if branch == 'master':
                local('git checkout master')
            else:
                local('git checkout -b %s origin/%s' % (branch, branch))

    def push(self, branch):
        with lcd(self.path):
            local('git push --tags origin %s' % branch)

    def tag(self, tag, message):
        with lcd(self.path):
            local('git tag -a %s -m "%s"' % (tag, message))

    def commit(self, version):
        with lcd(self.path):
            local('git commit -m "[xbmcswift2-release-script] prepare release %s"' % version)


def bump_minor(version_str):
    left, right = version_str.rsplit('.', 1)
    right = int(right) + 1
    return '%s.%s' % (left, right)

def get_addon_version(addon_dir):
    filename = os.path.join(addon_dir, 'addon.xml')
    xml = ET.parse(filename).getroot()
    return xam.Addon(xml).version

def get_addon_id(addon_dir):
    filename = os.path.join(addon_dir, 'addon.xml')
    xml = ET.parse(filename).getroot()
    return xam.Addon(xml).id

def set_addon_version(addon_dir, version):
    filename = os.path.join(addon_dir, 'addon.xml')
    xml = ET.parse(filename).getroot()
    addon = xam.Addon(xml)
    addon.version = version
    write_file(filename, addon.to_xml_string())


def bump_version(addon_dir):
    current_version = get_addon_version(addon_dir)
    new_version = prompt('Specify new version number: ', default=bump_minor(current_version))
    set_addon_version(addon_dir, new_version)


def rmdir(path):
    puts('Removing dir %s' % path)
    try:
        shutil.rmtree(path)
    except OSError:
        pass


def copydir(src, dest):
    puts('Copying %s to %s' % (src, dest))
    shutil.copytree(src, dest)


def write_file(path, contents):
    puts('Writing content to %s' % path)
    with open(path, 'w') as out:
        out.write(contents)


def print_email(addon_id, version, git_url, tag, xbmc_version):
    lines = [
        'Mailing List Email',
        '------------------',
        '',
        'Subject: [git pull] %s' % addon_id,
        '*addon - %s' % addon_id,
        '*version - %s' % version,
        '*url - %s' % git_url,
        '*tag - %s' % tag,
        '*xbmc version - %s' % xbmc_version,
        '',
        '',
    ]

    for line in lines:
        puts(colors.cyan(line))

@task
def local_release(xbmc_version=None):
    if xbmc_version is None:
        abort('Must specify an XBMC version, [dharma, eden]')
    xbmc_version = xbmc_version.upper()
    if xbmc_version not in BRANCHES.keys():
        abort('Invalid XBMC version, [dharma, eden]')

    local_repo, dist_repo = release_prepare(xbmc_version)
    print 'Development release created at %s' % dist_repo.path


@task
def release(xbmc_version=None):
    if xbmc_version is None:
        abort('Must specify an XBMC version, [dharma, eden]')
    xbmc_version = xbmc_version.upper()
    if xbmc_version not in BRANCHES.keys():
        abort('Invalid XBMC version, [dharma, eden]')

    local_repo, dist_repo = release_prepare(xbmc_version)
    release_perform(xbmc_version, local_repo, dist_repo)


def release_prepare(xbmc_version):
    assert not os.path.exists(os.path.join(os.path.dirname(__file__), '.release')), 'Release in progress. Either `fab release:perform` or `fab release:clear`'
    parent_dir = tempfile.mkdtemp()
    dist_path = os.path.join(parent_dir, REPO_DIR)

    # First get the current git version so we can include this in the release
    local_repo = GitRepo(path=os.path.dirname(__file__))
    current_git_version =  local_repo.get_head_hash()
    log('Release using commit %s' % current_git_version)

    # Clone a fresh copy of the current dist repo
    log('Cloning fresh copy of distribution repo...')
    dist_repo = GitRepo(path=dist_path, remote_url=REPO_URL)
    dist_repo.clone(parent_dir)

    # Checkout the proper branch
    log('Using branch %s for the distribution repo...' % BRANCHES[xbmc_version])
    dist_repo.checkout_remote_branch(BRANCHES[xbmc_version])

    # We could rsync, but easier to just remove existing xbmcswift2 dir and
    # copy over the current version
    log('Removing old xbmcswift2 dir and copying over current version...')
    rmdir(os.path.join(dist_path, 'lib', 'xbmcswift2'))
    copydir(os.path.join(local_repo.path, 'xbmcswift2'),
            os.path.join(dist_path, 'lib', 'xbmcswift2'))

    # Remove the cli and mockxbmc packages as they are not necessary for XBMC
    # execution
    log('Removing unneccessary cli and mockxbmc packages...')
    rmdir(os.path.join(dist_path, 'lib', 'xbmcswift2', 'cli'))
    rmdir(os.path.join(dist_path, 'lib', 'xbmcswift2', 'mockxbmc'))

    # Now we need to add the current git HEAD to a file in the dist repo
    log('Adding deployed git hash to xbmcswift2_version file...')
    write_file(os.path.join(dist_path, 'xbmcswift2_version'),
               current_git_version)

    # Prompt user for new XBMC version
    log('Bumping version...')
    bump_version(dist_path)

    # open changelog in vim
    log('Opening changelog.txt for editing...')
    changelog = os.path.join(dist_path, 'changelog.txt')

    # if user doesn't want to continue they shouldu be able to :cq
    returncode = subprocess.check_call([EDITOR, changelog])

    # return both repos
    return local_repo, GitRepo(path=dist_path)


def release_perform(xbmc_version, local_repo, dist_repo):
    # Stage everything in the repo
    log('Staging all modified files in the distribution repo...')
    dist_repo.stage_all()

    # Get the current XBMC version
    version = get_addon_version(dist_repo.path)

    # Commit all staged changes and tag
    log('Commiting changes and tagging the release...')
    dist_repo.commit(version)
    dist_repo.tag(version, '%s v%s' % (xbmc_version, version))

    # Tag the local repo as well
    local_repo.tag('xbmc-%s' % version, 'XBMC distribution v%s' % version)

    # Push everything
    log('Pushing changes to remote...')
    dist_repo.push(BRANCHES[xbmc_version])

    puts(colors.green('Release performed.'))

    # write the email
    addon_id = get_addon_id(dist_repo.path)
    print_email(addon_id, version, REPO_PUBLIC_URL, version, xbmc_version.lower())
