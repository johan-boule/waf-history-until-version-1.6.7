#! /usr/bin/env python
# encoding: utf-8
# Thomas Nagy, 2005 (ita)

import os
import os.path
import sys
import cPickle
from Deptree import Deptree

import Environment
import Params
import Runner
import Object

def trace(msg):
	Params.trace(msg, 'Build')
def debug(msg):
	Params.debug(msg, 'Build')
def error(msg):
	Params.error(msg, 'Build')

class Build:
	def __init__(self):
		self.m_configs  = []   # environments
		self.m_tree     = None # dependency tree
		self.m_dirs     = []   # folders in the dependency tree to scan
		self.m_rootdir  = ''   # root of the build, in case if the build is moved ?

		Params.g_build=self

	def load(self):
		self.m_rootdir = os.path.abspath('.')
		if sys.platform=='win32': self.m_rootdir=self.m_rootdir[2:]
		try:
			file = open(Params.g_dbfile, 'rb')
			self.m_tree = cPickle.load(file)
			file.close()
		except:
			self.m_tree = Deptree()
		# reset the flags of the tree
		self.m_tree.m_root.tag(0)

	def store(self):
		file = open(Params.g_dbfile, 'wb')
		cPickle.dump(self.m_tree, file, -1)
		file.close()

	def set_bdir(self, path):
		trace("set_builddir")
		p = os.path.abspath(path)
		if sys.platform=='win32': p=p[2:]
		node = self.m_tree.ensure_directory(p)
		self.m_tree.m_bldnode = node
		Params.g_bldnode = node

	def set_default_env(self, filename):
		# update the hashtable to set the build_dir
		env = Environment.Environment()
		if not filename:
			error('passing a null filename to set_default_env')
			return
		env.load(filename)
		env.setup(env['tools'])
		Params.g_default_env = env.copy()
		#debug(Params.g_default_env)

	def set_srcdir(self, dir):
		trace("set_srcdir")
		p = os.path.abspath(dir)
		if sys.platform=='win32': p=p[2:]
		node=self.m_tree.ensure_node_from_path(p)
		self.m_tree.m_srcnode = node
		Params.g_srcnode = node
		# position in the source tree when reading scripts
		Params.g_curdirnode = node

	# TODO: does scanning folders in order matter ?
	def scandirs_old(self, paths):
		ldirs = (' '+paths).split()

		for sub_dir in ldirs:
			if not sub_dir: continue # TODO is this line really needed ???

			this_dir = os.path.join(self.m_rootdir, sub_dir)

			# scan the src directory and get the corresponding node
			srcnode = self.m_tree.ensure_node_from_path(this_dir)
			self.m_tree.scanner_srcdir(srcnode)

			# name of the corresponding in build folder
			#this_dir_bld = os.path.join(self.m_rootdir, b_dir, sub_dir)
			this_dir_bld = os.path.join(self.m_rootdir, self.m_tree.m_bldnode.m_name, sub_dir)
			# make sure there is a corresponding *Node* in the build folder
			bldnode = self.m_tree.ensure_directory(this_dir_bld)
			# now scan the build directory, passing the src dir as a source
			self.m_tree.mirror(srcnode, bldnode)

	def scandirs(self, paths):
		ldirs=paths.split()
		for sub_dir in ldirs:
			self.m_tree.scanner_mirror(sub_dir)

	def cleanup(self):
		self.m_tree.m_name2nodes={}
		self.m_tree.m_flags={}

		#debug("setting some stat value to a bldnode")
		#curnode = self.m_tree.m_bldnode
		#curnode = curnode.find_node(['src', 'main.cpp'])
		#curnode.m_tstamp = os.stat(curnode.abspath()).st_mtime
		#curnode.debug_time()

	# usual computation types - dist and distclean might come here too
	def clean(self):
		trace("clean called")

	def compile(self):
		trace("compile called")

		os.chdir( self.m_tree.m_bldnode.abspath() )

		Object.flush()
		generator = Runner.JobGenerator(self.m_tree)
		if Params.g_maxjobs <=1: executor = Runner.Serial(generator)
		else:                    executor = Runner.Parallel(generator, Params.g_maxjobs)
		trace("executor starting")
		executor.start()

		os.chdir( self.m_tree.m_srcnode.abspath() )

	def install(self):
		trace("install called")
		for obj in Object.g_allobjs:
			obj.install()
		

