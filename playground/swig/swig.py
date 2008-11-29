#! /usr/bin/env python
# encoding: UTF-8
# Petar Forai
# Thomas Nagy 2008

import re
import Task, Utils
from TaskGen import extension
from Configure import conf

SWIG_EXTS = ['.swig', '.i']

swig_str = '${SWIG} ${SWIGFLAGS} ${SRC}'
Task.simple_task_type('swig', swig_str, color='BLUE', before='cc cxx')

re_1 = re.compile(r'^%module.*?\s+([\w]+)\s*?$', re.M)
re_2 = re.compile('%include "(.*)"', re.M)
re_3 = re.compile('#include "(.*)"', re.M)

class swig_class_scanner(object):
	def __init__(self):
		Scan.scanner.__init__(self)
	def scan(self, task, node):
		env = task.m_env
		variant = node.variant(env)
		tree = Params.g_build

		lst_names = []
		lst_src = []

		# read the file
		fi = open(node.abspath(env), 'r')
		content = fi.read()
		fi.close()

		# module name, only for the .swig file
		names = re_1.findall(content)
		if names: lst_names.append(names[0])

		# find .i files (and perhaps .h files)
		names = re_2.findall(content)
		for n in names:
			u = node.m_parent.find_source(n)
			if u: lst_src.append(u)

		# find project headers
		names = re_3.findall(content)
		for n in names:
			u = node.m_parent.find_source(n)
			if u: lst_src.append(u)

		# list of nodes this one depends on, and module name if present
		#print "result of ", node, lst_src, lst_names
		return (lst_src, lst_names)


# provide additional language processing
swig_langs = {}
def swig(fun):
	swig_langs[fun.__name__.replace('swig_', '')] = fun

@swig
def swig_python(tsk):
	tsk.set_outputs(tsk.inputs[0].parent.find_or_declare(tsk.module + '.py'))

@swig
def swig_ocaml(tsk):
	tsk.set_outputs(tsk.inputs[0].parent.find_or_declare(tsk.module + '.ml'))
	tsk.set_outputs(tsk.inputs[0].parent.find_or_declare(tsk.module + '.mli'))

@extension(SWIG_EXTS)
def i_file(self, node):
	flags = self.to_list(getattr(self, 'swig_flags', []))

	ext = '.swigwrap.c'
	if '-c++' in flags:
		ext += 'xx'

	if not '-outdir' in flags:
		flags.append('-outdir')
		flags.append(node.parent.abspath(self.env))

	# the user might specify the module directly
	module = getattr(self, 'swig_module', None)
	if not module:
		# else, open the files and search
		#txt = node.read(tsk.env)
		module = 'swigdemo'
	out_node = node.parent.find_or_declare(module + ext)

	# the task instance
	tsk = self.create_task('swig')
	tsk.set_inputs(node)
	tsk.set_outputs(out_node)
	tsk.module = module
	tsk.env['SWIGFLAGS'] = flags

	# add the language-specific output files as nodes
	# call funs in the dict swig_langs
	for x in flags:
		# obtain the language
		x = x[1:]
		try:
			fun = swig_langs[x]
		except KeyError:
			pass
		else:
			fun(tsk)

	self.allnodes.append(out_node)

@conf
def check_swig_version(conf, minver=None):
	"""Check for a minimum swig version  like conf.check_swig_version('1.3.28')
	or conf.check_swig_version((1,3,28)) """
	reg_swig = re.compile(r'SWIG Version\s(.*)', re.M)

	swig_out = Utils.cmd_output('%s -version' % conf.env['SWIG'])

	swigver = [int(s) for s in reg_swig.findall(swig_out)[0].split('.')]
	if isinstance(minver, basestring):
		minver = [int(s) for s in minver.split(".")]
	if isinstance(minver, tuple):
		minver = [int(s) for s in minver]
	result = (minver is None) or (minver[:3] <= swigver[:3])
	swigver_full = '.'.join(map(str, swigver))
	if result:
		conf.env['SWIG_VERSION'] = swigver_full
	minver_str = '.'.join(map(str, minver))
	if minver is None:
		conf.check_message_custom('swig version', '', swigver_full)
	else:
		conf.check_message('swig version', '>= %s' % (minver_str,), result, option=swigver_full)
	return result

def detect(conf):
	swig = conf.find_program('swig', var='SWIG')
	env = conf.env
	env['SWIG']      = swig
	env['SWIGFLAGS'] = ''
	env['SWIG_EXT']  = ['.swig']

