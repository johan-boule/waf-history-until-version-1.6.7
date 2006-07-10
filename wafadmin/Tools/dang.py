#! /usr/bin/env python
# encoding: utf-8
# Thomas Nagy, 2006 (ita)

import os, shutil, sys
import Action, Common, Object, Task, Params, Runner, Utils, Scan, cpp
from Params import debug, error, trace, fatal

# This function (hook) is called when the class cppobj encounters a '.coin' file
# .coin -> .cpp -> .o
def coin_file(obj, node):
	# Create the task for the coin file
	# the action 'dang' above is called for this
	# the number '4' in the parameters is the priority of the task
	# * lower number means high priority
	# * odd means the task can be run in parallel with others of the same priority number
	cointask = obj.create_task('dang', obj.env, 4)
	cointask.set_inputs(node)
	cointask.set_outputs(node.change_ext('.cpp'))

	# for debugging a task, use the following code:
	#cointask.debug(1)

	# now we also add the task that creates the object file ('.o' file)
	cpptask = obj.create_task('cpp', obj.env)
	cpptask.set_inputs(cointask.m_outputs)
	cpptask.set_outputs(node.change_ext('.o'))
	obj.p_compiletasks.append(cpptask)

def setup(env):
	# create our action, for use with coin_file
	Action.simple_action('dang', '${DANG} ${SRC} > ${TGT}', color='BLUE')

	# register the hook for use with cppobj
	if not env['handlers_cppobj_.coin']: env['handlers_cppobj_.coin'] = coin_file

def detect(conf):
	dang = conf.checkProgram('cat', var='CAT')
	if not dang: return 0
	conf.env['DANG'] = dang
	return 1

