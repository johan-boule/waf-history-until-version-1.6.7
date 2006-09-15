#! /usr/bin/env python
# encoding: utf-8
# Thomas Nagy, 2005 (ita)

import os,sys,string, types, imp
import Params
from Params import debug, error

class Environment:
	"A safe-to-use dictionary, but do not attach functions to it please (break cPickle)"
	def __init__(self):
		self.m_table={}
		# may be there is a better place for this
		if sys.platform == "win32": self.m_table['WINDOWS']=1

		# set the prefix once and for everybody on creation (configuration)
		self.m_table['PREFIX'] = Params.g_options.prefix

	def set_variant(self, name):
		self.m_table['_VARIANT_'] = name

	def variant(self):
		return self.m_table.get('_VARIANT_', 'default')

	def copy(self):
		newenv = Environment()
		newenv.m_table = self.m_table.copy()
		return newenv

	def setup(self, tool, tooldir=None):
		"setup tools for build process"
		if type(tool) is types.ListType:
			for i in tool: self.setup(i)
			return

		if not tooldir: tooldir = Params.g_tooldir
	
		file,name,desc = imp.find_module(tool, tooldir)
		module = imp.load_module(tool,file,name,desc)
		try:
			module.setup(self)
		except:
			error("setup function missing in tool: %s " % str(tool))
			raise
		if file: file.close()

	def __str__(self):
		return "environment table\n"+str(self.m_table)

	def __getitem__(self, key):
		try: return self.m_table[key]
		except:
			try: return Params.globals(key)
			except: return []
	def __setitem__(self, key, value):
		self.m_table[key] = value

	def appendValue(self, var, value):
		if type(value) is types.ListType: val = value
		else: val = [value]
		#print var, self[var]
		try: self.m_table[var] = self[var] + val
		except TypeError: self.m_table[var] = [self[var]] + val

	def prependValue(self, var, value):
		if type(value) is types.ListType: val = value
		else: val = [value]
		#print var, self[var]
		try: self.m_table[var] = val + self[var]
		except TypeError: self.m_table[var] = val + [self[var]]

	def appendUnique(self, var, value):
		if not self[var]:
			self[var]=value
		if value in self[var]: return
		self.appendValue(var, value)

	def store(self, filename):
		"Write the variables into a file"
		file=open(filename, 'w')
		keys=self.m_table.keys()
		keys.sort()
		file.write('#VERSION=%s\n' % Params.g_version)
		for key in keys:
			file.write('%s = %r\n'%(key,self.m_table[key]))
		file.close()

	def load(self, filename):
		"Retrieve the variables from a file"
		if not os.path.isfile(filename): return 0
		file=open(filename, 'r')
		for line in file:
			ln = line.strip()
			if not ln: continue
			if ln[:9]=='#VERSION=':
				if ln[9:] != Params.g_version: error('waf version mismatch, you should perhaps reconfigure')
			if ln[0]=='#': continue
			(key,value) = string.split(ln, '=', 1)
			line = 'self.m_table["%s"] = %s'%(key.strip(), value.strip())
			exec line
		file.close()
		debug(self.m_table)
		return 1

	def get_destdir(self):
		"return the destdir, useful for installing"
		if self.m_table.has_key('NOINSTALL'): return ''
		dst = Params.g_options.destdir
		try: dst = dst+os.sep+self.m_table['SUBDEST']
		except: pass
		return dst

	def hook(self, classname, ext, func):
		import Object
		Object.hook(classname, ext, func)

