#!/usr/bin/env python
# encoding: utf-8
# Stian Selnes, 2008
# Thomas Nagy 2009-2010 (ita)

import os, sys
from waflib.Tools import ccroot, ar, gcc
from waflib.Configure import conf

@conf
def find_icc(conf):
	if sys.platform == 'cygwin':
		conf.fatal('The Intel compiler does not work on Cygwin')

	v = conf.env
	cc = None
	if v['CC']: cc = v['CC']
	elif 'CC' in conf.environ: cc = conf.environ['CC']
	if not cc: cc = conf.find_program('icc', var='CC')
	if not cc: cc = conf.find_program('ICL', var='CC')
	if not cc: conf.fatal('Intel C Compiler (icc) was not found')
	cc = conf.cmd_to_list(cc)

	conf.get_cc_version(cc, icc=True)
	v['CC'] = cc
	v['CC_NAME'] = 'icc'

detect = '''
find_icc
find_ar
gcc_common_flags
gcc_modifier_platform
cc_load_tools
cc_add_flags
link_add_flags
'''
