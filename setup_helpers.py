# emacs: -*- mode: python; py-indent-offset: 4; indent-tabs-mode: nil -*-
# vi: set ft=python sts=4 ts=4 sw=4 et:
"""
Build helpers for setup.py

Includes package dependency checks, and code to build the documentation

To build the docs, run::

    python setup.py build_sphinx

This module has to work for python 2 and python 3.
"""
from __future__ import with_statement

# Standard library imports
import sys
import os
from os.path import join as pjoin, dirname
import zipfile
import warnings
import shutil
from distutils.cmd import Command
from distutils.command.clean import clean
from distutils.command.build_py import build_py
from distutils.version import LooseVersion
from distutils.dep_util import newer_group
from distutils.errors import DistutilsError

try:
    from ConfigParser import ConfigParser
except ImportError:  # Python 3
    from configparser import ConfigParser

from numpy.distutils.misc_util import appendpath
from numpy.distutils import log

# Sphinx import
try:
    from sphinx.setup_command import BuildDoc
except ImportError:
    have_sphinx = False
else:
    have_sphinx = True

# Get project related strings.  Please do not change this line to use
# execfile because execfile is not available in Python 3
_info_fname = pjoin('nipy', 'info.py')
INFO_VARS = {}
exec(open(_info_fname, 'rt').read(), {}, INFO_VARS)

DOC_BUILD_DIR = os.path.join('build', 'html')

CYTHON_MIN_VERSION = INFO_VARS['CYTHON_MIN_VERSION']

################################################################################
# Distutils Command class for installing nipy to a temporary location. 
class TempInstall(Command):
    temp_install_dir = os.path.join('build', 'install')

    def run(self):
        """ build and install nipy in a temporary location. """
        install = self.distribution.get_command_obj('install')
        install.install_scripts = self.temp_install_dir
        install.install_base    = self.temp_install_dir
        install.install_platlib = self.temp_install_dir 
        install.install_purelib = self.temp_install_dir 
        install.install_data    = self.temp_install_dir 
        install.install_lib     = self.temp_install_dir 
        install.install_headers = self.temp_install_dir 
        install.run()

        # Horrible trick to reload nipy with our temporary instal
        for key in sys.modules.keys():
            if key.startswith('nipy'):
                sys.modules.pop(key, None)
        sys.path.append(os.path.abspath(self.temp_install_dir))
        # Pop the cwd
        sys.path.pop(0)
        import nipy

    def initialize_options(self):
        pass

    def finalize_options(self):
        pass


################################################################################
# Distutils Command class for API generation 
class APIDocs(TempInstall):
    description = \
    """generate API docs """

    user_options = [
        ('None', None, 'this command has no options'),
        ]


    def run(self):
        # First build the project and install it to a temporary location.
        TempInstall.run(self)
        os.chdir('doc')
        try:
            # We are running the API-building script via an
            # system call, but overriding the import path.
            toolsdir = os.path.abspath(pjoin('..', 'tools'))
            build_templates = pjoin(toolsdir, 'build_modref_templates.py')
            cmd = """%s -c 'import sys; sys.path.append("%s"); sys.path.append("%s"); execfile("%s", dict(__name__="__main__"))'""" \
                % (sys.executable, 
                   toolsdir,
                   self.temp_install_dir,
                   build_templates)
            os.system(cmd)
        finally:
            os.chdir('..')


################################################################################
# Code to copy the sphinx-generated html docs in the distribution.
def relative_path(filename):
    """ Return the relative path to the file, assuming the file is
        in the DOC_BUILD_DIR directory.
    """
    length = len(os.path.abspath(DOC_BUILD_DIR)) + 1
    return os.path.abspath(filename)[length:]



################################################################################
# Distutils Command class to clean
class Clean(clean):

    def run(self):
        clean.run(self)
        api_path = os.path.join('doc', 'api', 'generated')
        if os.path.exists(api_path):
            print("Removing %s" % api_path)
            shutil.rmtree(api_path)
        if os.path.exists(DOC_BUILD_DIR):
            print("Removing %s" % DOC_BUILD_DIR)
            shutil.rmtree(DOC_BUILD_DIR)


################################################################################
# Distutils Command class build the docs
if have_sphinx:
    class MyBuildDoc(BuildDoc):
        """ Sub-class the standard sphinx documentation building system, to
            add logics for API generation and matplotlib's plot directive.
        """

        def run(self):
            self.run_command('api_docs')
            # We need to be in the doc directory for to plot_directive
            # and API generation to work
            os.chdir('doc')
            try:
                BuildDoc.run(self)
            finally:
                os.chdir('..')
            self.zip_docs()

        def zip_docs(self):
            if not os.path.exists(DOC_BUILD_DIR):
                raise OSError('Doc directory does not exist.')
            target_file = os.path.join('doc', 'documentation.zip')
            # ZIP_DEFLATED actually compresses the archive. However, there
            # will be a RuntimeError if zlib is not installed, so we check
            # for it. ZIP_STORED produces an uncompressed zip, but does not
            # require zlib.
            try:
                zf = zipfile.ZipFile(target_file, 'w', 
                                            compression=zipfile.ZIP_DEFLATED)
            except RuntimeError:
                warnings.warn('zlib not installed, storing the docs '
                                'without compression')
                zf = zipfile.ZipFile(target_file, 'w', 
                                            compression=zipfile.ZIP_STORED)    

            for root, dirs, files in os.walk(DOC_BUILD_DIR):
                relative = relative_path(root)
                if not relative.startswith('.doctrees'):
                    for f in files:
                        zf.write(os.path.join(root, f), 
                                os.path.join(relative, 'html_docs', f))
            zf.close()

        def finalize_options(self):
            """ Override the default for the documentation build
                directory.
            """
            self.build_dir = os.path.join(*DOC_BUILD_DIR.split(os.sep)[:-1])
            BuildDoc.finalize_options(self)

else: # failed Sphinx import
    # Raise an error when trying to build docs
    class MyBuildDoc(Command):
        user_options = []
        def run(self):
            raise ImportError(
                "Sphinx is not installed, docs cannot be built")
        def initialize_options(self):
            pass
        def finalize_options(self):
            pass


def have_good_cython():
    try:
        from Cython.Compiler.Version import version
    except ImportError:
        return False
    return LooseVersion(version) >= LooseVersion(CYTHON_MIN_VERSION)


def generate_a_pyrex_source(self, base, ext_name, source, extension):
    ''' Monkey patch for numpy build_src.build_src method

    Uses Cython instead of Pyrex.
    '''
    good_cython = have_good_cython()
    if self.inplace or not good_cython:
        target_dir = dirname(base)
    else:
        target_dir = appendpath(self.build_src, dirname(base))
    target_file = pjoin(target_dir, ext_name + '.c')
    depends = [source] + extension.depends
    sources_changed = newer_group(depends, target_file, 'newer') 
    if self.force or sources_changed:
        if good_cython:
            # add distribution (package-wide) include directories, in order
            # to pick up needed .pxd files for cython compilation
            incl_dirs = extension.include_dirs[:]
            dist_incl_dirs = self.distribution.include_dirs
            if dist_incl_dirs is not None:
                incl_dirs += dist_incl_dirs
            import Cython.Compiler.Main
            log.info("cythonc:> %s" % (target_file))
            self.mkpath(target_dir)
            options = Cython.Compiler.Main.CompilationOptions(
                defaults=Cython.Compiler.Main.default_options,
                include_path=incl_dirs,
                output_file=target_file)
            cython_result = Cython.Compiler.Main.compile(source,
                                                       options=options)
            if cython_result.num_errors != 0:
                raise DistutilsError("%d errors while compiling "
                                     "%r with Cython"
                                     % (cython_result.num_errors, source))
        elif sources_changed and os.path.isfile(target_file):
            raise DistutilsError("Cython >=%s required for compiling %r"
                                 " because sources (%s) have changed" %
                                 (CYTHON_MIN_VERSION, source, ','.join(depends)))
        else:
            raise DistutilsError("Cython >=%s required for compiling %r"
                                 " but not available" %
                                 (CYTHON_MIN_VERSION, source))
    return target_file


# Copied from soon-to-be retired nibabel/nisext/sexts.py
# We'll probably drop this way of doing versioning soon
def get_comrec_build(pkg_dir, build_cmd=build_py):
    """ Return extended build command class for recording commit

    The extended command tries to run git to find the current commit, getting
    the empty string if it fails.  It then writes the commit hash into a file
    in the `pkg_dir` path, named ``COMMIT_INFO.txt``.

    In due course this information can be used by the package after it is
    installed, to tell you what commit it was installed from if known.

    To make use of this system, you need a package with a COMMIT_INFO.txt file -
    e.g. ``myproject/COMMIT_INFO.txt`` - that might well look like this::

        # This is an ini file that may contain information about the code state
        [commit hash]
        # The line below may contain a valid hash if it has been substituted during 'git archive'
        archive_subst_hash=$Format:%h$
        # This line may be modified by the install process
        install_hash=

    The COMMIT_INFO file above is also designed to be used with git substitution
    - so you probably also want a ``.gitattributes`` file in the root directory
    of your working tree that contains something like this::

       myproject/COMMIT_INFO.txt export-subst

    That will cause the ``COMMIT_INFO.txt`` file to get filled in by ``git
    archive`` - useful in case someone makes such an archive - for example with
    via the github 'download source' button.

    Although all the above will work as is, you might consider having something
    like a ``get_info()`` function in your package to display the commit
    information at the terminal.  See the ``pkg_info.py`` module in the nipy
    package for an example.
    """
    class MyBuildPy(build_cmd):
        ''' Subclass to write commit data into installation tree '''
        def run(self):
            build_cmd.run(self)
            import subprocess
            proc = subprocess.Popen('git rev-parse --short HEAD',
                                    stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE,
                                    shell=True)
            repo_commit, _ = proc.communicate()
            # Fix for python 3
            repo_commit = str(repo_commit)
            # We write the installation commit even if it's empty
            cfg_parser = ConfigParser()
            cfg_parser.read(pjoin(pkg_dir, 'COMMIT_INFO.txt'))
            cfg_parser.set('commit hash', 'install_hash', repo_commit)
            out_pth = pjoin(self.build_lib, pkg_dir, 'COMMIT_INFO.txt')
            cfg_parser.write(open(out_pth, 'wt'))
    return MyBuildPy


# The command classes for distutils, used by setup.py
cmdclass = {'api_docs': APIDocs,
            'clean': Clean,
            'build_sphinx': MyBuildDoc}
