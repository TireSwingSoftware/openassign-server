"""
Merge test classes from multiple test suites into this namespace so that
they can be easily started by a typical Django test run.


This module also ensures when test classes are merged into a single
namepsace, there are no duplicates names.
"""

import inspect

from pr_services.testlib import TestCase

TEST_MODULES = (
        'pr_services.pr_tests',
        'pr_services.exam_system.tests',
        # more coming soon...
)

def _import_test_module(path, xlocals, xglobals):
    module = __import__(path, xglobals, xlocals, [], -1)
    suites = path.split('.')[1:]
    for suite in suites:
        module = getattr(module, suite)
    return module

def _test_class_filter(name__value):
    name, value = name__value
    if not isinstance(value, type):
        return False
    if not issubclass(value, TestCase) or value is TestCase:
        return False
    else:
        return name.startswith('Test')

def _setup_tests(xlocals, xglobals):
    for module_path in TEST_MODULES:
        module = _import_test_module(module_path, xlocals, xglobals)
        members = inspect.getmembers(module)
        classes = dict(filter(_test_class_filter, members))
        assert not any(name in xlocals or name in xglobals for name in classes)
        if xglobals:
            xglobals.update(classes)
        if xlocals:
            xlocals.update(classes)

_setup_tests(locals(), globals())
