#! /usr/bin/env python
# encoding: utf-8
# Thomas Nagy, 2008 (ita)

import sys, re, os

import Action, Object, Params, Scan, Common, Utils, preproc
from Params import error, debug, fatal, warning
from ccroot import ccroot

"""
if you want to use the code here, you must add the following two methods:
* apply_libtool
* apply_link_libtool

To do so, use a code similar to the following:
obj = obj.create(...)
obj.want_libtool = 1
obj.set_order('apply_libtool', 'apply_core')
obj.set_order('apply_link', 'apply_link_libtool')
"""

# fake libtool files
fakelibtool_vardeps = ['CXX', 'PREFIX']
def fakelibtool_build(task):
	# Writes a .la file, used by libtool
	env = task.env()
	dest  = open(task.m_outputs[0].abspath(env), 'w')
	sname = task.m_inputs[0].m_name
	fu = dest.write
	fu("# Generated by ltmain.sh - GNU libtool 1.5.18 - (pwn3d by BKsys II code name WAF)\n")
	if env['vnum']:
		nums = env['vnum'].split('.')
		libname = task.m_inputs[0].m_name
		name3 = libname+'.'+env['vnum']
		name2 = libname+'.'+nums[0]
		name1 = libname
		fu("dlname='%s'\n" % name2)
		strn = " ".join([name3, name2, name1])
		fu("library_names='%s'\n" % (strn) )
	else:
		fu("dlname='%s'\n" % sname)
		fu("library_names='%s %s %s'\n" % (sname, sname, sname) )
	fu("old_library=''\n")
	vars = ' '.join(env['libtoolvars']+env['LINKFLAGS'])
	fu("dependency_libs='%s'\n" % vars)
	fu("current=0\n")
	fu("age=0\nrevision=0\ninstalled=yes\nshouldnotlink=no\n")
	fu("dlopen=''\ndlpreopen=''\n")
	fu("libdir='%s/lib'\n" % env['PREFIX'])
	dest.close()
	return 0

def read_la_file(path):
	sp = re.compile(r'^([^=]+)=\'(.*)\'$')
	dc={}
	file = open(path, "r")
	for line in file.readlines():
		try:
			#print sp.split(line.strip())
			_, left, right, _ = sp.split(line.strip())
			dc[left]=right
		except ValueError:
			pass
	file.close()
	return dc

def apply_link_libtool(self):
	if not getattr(self, 'want_libtool', 0): return

	if self.m_type != 'program':
		linktask = self.link_task
		latask = self.create_task('fakelibtool', self.env)
		latask.set_inputs(linktask.m_outputs)
		latask.set_outputs(linktask.m_outputs[0].change_ext('.la'))
		self.m_latask = latask

	if not (Params.g_commands['install'] or Params.g_commands['uninstall']): return
	self.install_results(dest_var, dest_subdir, self.m_latask)
setattr(ccroot, 'apply_link_libtool', apply_link_libtool)

def apply_libtool(self):
	if getattr(self, 'want_libtool', 0) <= 0: return

	self.env['vnum']=self.vnum

	paths=[]
	libs=[]
	libtool_files=[]
	libtool_vars=[]

	for l in self.env['LINKFLAGS']:
		if l[:2]=='-L':
			paths.append(l[2:])
		elif l[:2]=='-l':
			libs.append(l[2:])

	for l in libs:
		for p in paths:
			dict = read_la_file(p+'/lib'+l+'.la')
			linkflags2 = dict.get('dependency_libs', '')
			for v in linkflags2.split():
				if v.endswith('.la'):
					libtool_files.append(v)
					libtool_vars.append(v)
					continue
				self.env.append_unique('LINKFLAGS', v)
				break

	self.env['libtoolvars']=libtool_vars

	while libtool_files:
		file = libtool_files.pop()
		dict = read_la_file(file)
		for v in dict['dependency_libs'].split():
			if v[-3:] == '.la':
				libtool_files.append(v)
				continue
			self.env.append_unique('LINKFLAGS', v)
setattr(ccroot, 'apply_libtool', apply_libtool)

Action.Action('fakelibtool', vars=fakelibtool_vardeps, func=fakelibtool_build, color='BLUE', prio=200)


