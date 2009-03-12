#!/usr/bin/env python
# encoding: utf-8
# Thomas Nagy, 2006-2008 (ita)
# Ralf Habacker, 2006 (rh)

"ar and ranlib"

import os, sys
import Task
from Configure import conftest

ar_str = '${AR} ${ARFLAGS} ${TGT} ${SRC}'
cls = Task.simple_task_type('ar_link_static', ar_str, color='YELLOW', ext_in='.o')
cls.maxjobs = 1

# remove the output in case it already exists
# yinon: you may uncomment this once you have a proof it is necessary
"""
old = cls.run
def wrap(self):
	try: os.remove(self.outputs[0].abspath(self.env))
	except OSError: pass
	return old(self)
setattr(cls, 'run', wrap)
"""

def detect(conf):
	comp = conf.find_program('ar', var='AR')
	if not comp: return

	ranlib = conf.find_program('ranlib', var='RANLIB')
	if not ranlib: return

	v = conf.env
	v['AR']          = comp
	v['ARFLAGS']     = 'rc'
	v['RANLIB']      = ranlib
	v['RANLIBFLAGS'] = ''

@conftest
def find_ar(conf):
	v = conf.env
	conf.check_tool('ar')
	if not v['AR']: conf.fatal('ar is required for static libraries - not found')


