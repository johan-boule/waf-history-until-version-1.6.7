#! /usr/bin/env python
# encoding: utf-8
# Yinon Ehrlich, 2008

"""
cc_family_test:
a root tester for all c-compilers tools, like gcc, suncc, msvc.
"""

import os
from ccroot_test import CcRootTester

class CcFamilyTester(CcRootTester):
	def __init__(self, methodName):
		self.object_name	= 'cc'
		CcRootTester.__init__(self, methodName)

	def test_simple_cpp_program_fails(self):
		# simple default cpp program, should fail !
		self._setup_cpp_program()
		self._test_configure()
		self._test_build(False) # test for failure

	def test_simple_cpp_object_fails(self):
		# simple default cpp object of executable, should fail !
		self._setup_cpp_objects()
		self._test_configure()
		self._test_build(False) # test for failure

	def test_c_program(self):
		# simple default program 
		self._setup_c_program()
		self._test_configure()
		self._test_build()
		self._test_run( os.path.join("build", "default", "hello") )

	def test_c_object(self):
		# simple default object 
		self._setup_c_objects()
		self._test_configure()
		self._test_build()
	
	# TODO:
	# --debug_level is not working now, to restore the tests for the various level,
	# refer to older versions.
	# for example: 
	# http://code.google.com/p/waf/source/browse/tags/waf-1.4.2/wafadmin/test/cc_family_test.py
	