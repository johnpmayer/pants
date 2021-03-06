# coding=utf-8
# Copyright 2016 Pants project contributors (see CONTRIBUTORS.md).
# Licensed under the Apache License, Version 2.0 (see LICENSE).

from __future__ import absolute_import, division, print_function, unicode_literals

import os
from contextlib import contextmanager
from textwrap import dedent

from pants.base.build_environment import get_buildroot
from pants.util.dirutil import safe_open
from pants_test.pants_run_integration_test import PantsRunIntegrationTest
from pants_test.testutils.file_test_util import exact_files


_NAMESPACE = dedent(
    """
    namespace go thrifttest.duck
    """)
_DUCK_STRUCT =  dedent(
    """
    struct Duck {
      1: optional string quack,
    }
    """)
_FEEDER_STRUCT_TEMPLATE =  dedent(
    """
    service Feeder {{
      void feed(1:{include}Duck duck),
    }}
    """)


class GoThriftGenIntegrationTest(PantsRunIntegrationTest):

  @contextmanager
  def _create_thrift_project(self, thrift_files):
    with self.temporary_sourcedir() as srcdir:
      for path, content in thrift_files.items():
        with safe_open(os.path.join(srcdir, path), 'w') as fp:
          fp.write(content)
      with safe_open(os.path.join(srcdir, 'src/thrift/thrifttest/BUILD'), 'w') as fp:
        fp.write(dedent("""
            go_thrift_library(
              name='fleem',
              sources=globs('*.thrift'),
            )
            """).strip())

      with safe_open(os.path.join(srcdir, 'src/go/usethrift/example.go'), 'w') as fp:
        fp.write(dedent("""
            package usethrift

            import "thrifttest/duck"

            func whatevs(f duck.Feeder) string {
              d := duck.NewDuck()
              f.Feed(d)
              return d.GetQuack()
            }
            """).strip())
      with safe_open(os.path.join(srcdir, 'src/go/usethrift/BUILD'), 'w') as fp:
        fp.write(dedent("""
            go_library(
              dependencies=[
                '{srcdir}/src/thrift/thrifttest:fleem'
              ]
            )
            """.format(srcdir=os.path.relpath(srcdir, get_buildroot()))).strip())

      with safe_open(os.path.join(srcdir, '3rdparty/go/github.com/apache/thrift/BUILD'), 'w') as fp:
        fp.write("go_remote_library(rev='0.9.3', pkg='lib/go/thrift')")

      config = {
        'gen.go-thrift': {
          'thrift_import_target':
              os.path.join(os.path.relpath(srcdir, get_buildroot()),
                           '3rdparty/go/github.com/apache/thrift:lib/go/thrift'),
          'thrift_import': 'github.com/apache/thrift/lib/go/thrift'
        }
      }
      yield srcdir, config

  def test_go_thrift_gen_single(self):
    # Compile with one thrift file.
    thrift_files = {
        'src/thrift/thrifttest/duck.thrift':
          _NAMESPACE + _DUCK_STRUCT + _FEEDER_STRUCT_TEMPLATE.format(include=''),
      }
    with self.temporary_workdir() as workdir:
      with self._create_thrift_project(thrift_files) as (srcdir, config):
        args = [
            'compile',
            os.path.join(srcdir, 'src/go/usethrift')
          ]
        pants_run = self.run_pants_with_workdir(args, workdir, config=config)
        self.assert_success(pants_run)

        # Fetch the hash for task impl version.
        go_thrift_contents = [p for p in os.listdir(os.path.join(workdir, 'gen', 'go-thrift'))
                              if p != 'current']  # Ignore the 'current' symlink.
        self.assertEqual(len(go_thrift_contents), 1)
        hash_dir = go_thrift_contents[0]

        target_dir = os.path.relpath(os.path.join(srcdir, 'src/thrift/thrifttest/fleem'),
                                     get_buildroot())
        root = os.path.join(workdir, 'gen', 'go-thrift', hash_dir,
                            target_dir.replace(os.path.sep, '.'), 'current')

        self.assertEqual(sorted(['src/go/thrifttest/duck/constants.go',
                                  'src/go/thrifttest/duck/ttypes.go',
                                  'src/go/thrifttest/duck/feeder.go',
                                  'src/go/thrifttest/duck/feeder-remote/feeder-remote.go']),
                          sorted(exact_files(root)))

  def test_go_thrift_gen_multi(self):
    # Compile with a namespace split across thrift files.
    duck_include = dedent(
        """
        include "thrifttest/duck.thrift"
        """)
    thrift_files = {
        'src/thrift/thrifttest/duck.thrift': _NAMESPACE + _DUCK_STRUCT,
        'src/thrift/thrifttest/feeder.thrift':
          _NAMESPACE + duck_include + _FEEDER_STRUCT_TEMPLATE.format(include='duck.'),
      }
    with self.temporary_workdir() as workdir:
      with self._create_thrift_project(thrift_files) as (srcdir, config):
        args = [
            # Necessary to use a newer thrift version.
            '--thrift-version=0.10.0',
            'compile',
            os.path.join(srcdir, 'src/go/usethrift')
          ]
        pants_run = self.run_pants_with_workdir(args, workdir, config=config)
        self.assert_success(pants_run)
