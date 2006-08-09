#! /usr/bin/env python
# encoding: utf-8
# Thomas Nagy, 2006 (ita)

# found is 1, not found is 0

import os, sys
import Utils, Params, Action, Object, Runner, Common
from Params import debug, error, trace, fatal


native_lst=['native', 'all', 'c_object']
bytecode_lst=['bytecode', 'all']
class ocamlobj(Object.genobj):
	s_default_ext = ['.mli', '.mll', '.mly', '.ml']
	def __init__(self, type='all', library=0):
		Object.genobj.__init__(self, 'ocaml')

		self.m_type       = type
		self.m_source     = ''
		self.m_target     = ''
		self.islibrary    = library
		self._incpaths_lst = []
		self._bld_incpaths_lst = []
		self._mlltasks    = []
		self._mlytasks    = []

		self._mlitasks    = []
		self._native_tasks   = []
		self._bytecode_tasks = []

		self.bytecode_env = None
		self.native_env   = None

		self.includes     = ''
		self.uselib       = ''

		# TODO
		self.are_deps_set = 0

		if not self.env: self.env = Params.g_build.m_allenvs['default']

		if not type in ['bytecode','native','all','c_object']:
			print 'type for camlobj is undefined '+type
			type='all'

		if type in native_lst:
			self.native_env                = self.env.copy()
			self.native_env['OCAMLCOMP']   = self.native_env['OCAMLOPT']
			self.native_env['OCALINK']     = self.native_env['OCAMLOPT']
		if type in bytecode_lst:
			self.bytecode_env              = self.env.copy()
			self.bytecode_env['OCAMLCOMP'] = self.bytecode_env['OCAMLC']
			self.bytecode_env['OCALINK']   = self.bytecode_env['OCAMLC']

		if self.islibrary:
			self.bytecode_env['OCALINKFLAGS'] = '-a'
			self.native_env['OCALINKFLAGS']   = '-a'

		if self.m_type == 'c_object':
			self.native_env['OCALINK'] = self.native_env['OCALINK']+' -output-obj'

	def apply_incpaths(self):
		inc_lst = self.includes.split()
		lst = self._incpaths_lst
		tree = Params.g_build
		for dir in inc_lst:
			node = self.m_current_path.find_node( dir.split(os.sep) )
			if not node:
				error("node not found dammit")
				continue
			Params.g_build.rescan(node)
			if not node in lst: lst.append( node )
			self._bld_incpaths_lst.append(node)
		# now the nodes are added to self._incpaths_lst

	def apply(self):
		self.apply_incpaths()

		for i in self._incpaths_lst:
			if self.bytecode_env:
				self.bytecode_env.appendValue('OCAMLPATH', '-I %s' % i.srcpath(self.env))
				self.bytecode_env.appendValue('OCAMLPATH', '-I %s' % i.bldpath(self.env))

			if self.native_env:
				self.native_env.appendValue('OCAMLPATH', '-I %s' % i.bldpath(self.env))
				self.native_env.appendValue('OCAMLPATH', '-I %s' % i.srcpath(self.env))

		varnames = ['INCLUDES', 'OCALINKFLAGS', 'OCALINKFLAGS_OPT']
		for name in self.uselib.split():
			for vname in varnames:
				cnt = self.env[vname+'_'+name]
				if cnt:
					if self.bytecode_env: self.bytecode_env.appendValue(vname, cnt)
					if self.native_env: self.native_env.appendValue(vname, cnt)

		source_lst = self.source.split()
		nodes_lst = []

		# first create the nodes corresponding to the sources
		for filename in source_lst:
			base, ext = os.path.splitext(filename)
			node = self.file_in(filename)[0]
			if not ext in self.s_default_ext:
				print "??? ", filename

			if ext == '.mll':
				mll_task = self.create_task('ocamllex', self.native_env, 1)
				mll_task.set_inputs(node)
				mll_task.set_outputs(node.change_ext('.ml'))
				self._mlltasks.append(mll_task)

				node = mll_task.m_outputs[0]

			elif ext == '.mly':
				mly_task = self.create_task('ocamlyacc', self.native_env, 1)
				mly_task.set_inputs(node)
				mly_task.set_outputs([node.change_ext('.ml'), node.change_ext('.mli')])
				self._mlytasks.append(mly_task)

				task = self.create_task('ocamlcmi', self.native_env, 4)
				task.set_inputs(mly_task.m_outputs[1])
				task.set_outputs(mly_task.m_outputs[1].change_ext('.cmi'))

				node = mly_task.m_outputs[0]
			elif ext == '.mli':
				task = self.create_task('ocamlcmi', self.native_env, 4)
				task.set_inputs(node)
				task.set_outputs(node.change_ext('.cmi'))
				self._mlitasks.append(task)
				continue
			elif ext == '.c':
				task = self.create_task('ocamlcc', self.native_env, 6)
				task.set_inputs(node)
				task.set_outputs(node.change_ext('.o'))

				self.out_nodes += task.m_outputs
				continue
			else:
				pass

			if self.native_env:
				task = self.create_task('ocaml', self.native_env, 6)
				task.set_inputs(node)
				task.set_outputs(node.change_ext('.cmx'))
				self._native_tasks.append(task)
			if self.bytecode_env:
				task = self.create_task('ocaml', self.bytecode_env, 6)
				task.set_inputs(node)
				task.set_outputs(node.change_ext('.cmo'))
				self._bytecode_tasks.append(task)

		if self.bytecode_env:
			linktask = self.create_task('ocalink', self.bytecode_env, 101)
			objfiles = []
			for t in self._bytecode_tasks: objfiles.append(t.m_outputs[0])
			linktask.m_inputs  = objfiles
			linktask.m_outputs = self.file_in(self.get_target_name(bytecode=1))

		if self.native_env:
			linktask = self.create_task('ocalinkopt', self.native_env, 101)
			objfiles = []
			for t in self._native_tasks: objfiles.append(t.m_outputs[0])
			linktask.m_inputs  = objfiles
			linktask.m_outputs = self.file_in(self.get_target_name(bytecode=0))

			self.out_nodes += linktask.m_outputs

	def get_target_name(self, bytecode):
		if bytecode:
			if self.islibrary:
				return self.target+'.cma'
			else:
				return self.target+'.run'
		else:
			if self.m_type == 'c_object': return self.target+'.o'

			if self.islibrary:
				return self.target+'.cmxa'
			else:
				return self.target

	def find_sources_in_dirs(self, dirnames, excludes=[]):
		lst=[]
		try:    exc_lst = excludes.split()
		except: exc_lst = excludes

		for name in dirnames.split():
			#print "name is ", name
			anode = Params.g_build.ensure_node_from_lst(self.m_current_path, name.split('/'))
			#print "anode ", anode.m_name, " ", anode.m_files
			Params.g_build.rescan(anode)
			#print "anode ", anode.m_name, " ", anode.m_files

			#node = self.m_current_path.find_node( name.split(os.sep) )
			for file in anode.m_files:
				#print "file found ->", file
				(base, ext) = os.path.splitext(file.m_name)
				if ext in self.s_default_ext:
					s = file.relpath(self.m_current_path)
					if not s in lst:
						if s in exc_lst: continue
						lst.append(s)

		self.source = self.source+' '+(" ".join(lst))

	def comptask(self):
		# use ocamldep to set the dependencies
		#
		# we cannot run this method when posting the object as the mly and mll tasks
		# are not run yet, so the resulting .ml and .mli files do not exist, leading to
		# incomplete dependencies

		curdir = self.m_current_path
		file2task = {}

		dirs  = []
		milst = []
		lst = []
		for i in self._mlitasks + self._nativetasks + self._bytecodetasks:
			node = i.m_inputs[0]
			path = node.bldpath(self.env)
			if not path in milst:
				milst.append(path)
				dir = node.m_parent.srcpath(self.env)
				if not dir in dirs: dirs.append(dir)

			m = i.m_outputs[0]
			file2task[m.bldpath(self.env)] = i

		cmd = ['ocamldep']
		for i in dirs:
			cmd.append('-I')
			cmd.append(i)
		for i in htbl:
			cmd.append(i)

		cmd = " ".join(cmd)
		ret = os.popen(cmd).read().strip()
		print ret

		#hashdeps = {}
		lines = ret.split('\n')
		for line in lines:
			lst = line.split(': ')
			#hashdeps[lst[0]] = lst[1].split()

			if lst[0] in file2task:
				t = file2task[lst[0]]

				for name in lst[1].split():
					if name in file2task:
						t.m_run_after.append(file2task[name])


def setup(env):
	Object.register('ocaml', ocamlobj)
	Action.simple_action('ocaml', '${OCAMLCOMP} ${OCAMLPATH} ${INCLUDES} -c -o ${TGT} ${SRC}', color='GREEN')
	Action.simple_action('ocalink', '${OCALINK} -o ${TGT} ${INCLUDES} ${OCALINKFLAGS} ${SRC}', color='YELLOW')
	Action.simple_action('ocalinkopt', '${OCALINK} -o ${TGT} ${INCLUDES} ${OCALINKFLAGS_OPT} ${SRC}', color='YELLOW')
	Action.simple_action('ocamlcmi', '${OCAMLC} ${OCAMLPATH} ${INCLUDES} -o ${TGT} -c ${SRC}', color='BLUE')
	Action.simple_action('ocamlcc', 'cd ${TGT[0].bld_dir(env)} && ${OCAMLOPT} ${OCAMLPATH} ${INCLUDES} -c ${SRC[0].abspath(env)}', color='GREEN')
	Action.simple_action('ocamllex', '${OCAMLLEX} ${SRC} -o ${TGT}', color='BLUE')
	Action.simple_action('ocamlyacc', '${OCAMLYACC} -b ${TGT[0].bldbase(env)} ${SRC}', color='BLUE')

def detect(conf):

	opt = conf.checkProgram('ocamlopt', var='OCAMLOPT')
	occ = conf.checkProgram('ocamlc', var='OCAMLC')
	if (not opt) or (not occ):
		fatal('The objective caml compiler was not found:\n' \
			'install it or make it availaible in your PATH')

	lex  = conf.checkProgram('ocamllex', var='OCAMLLEX')
	yacc = conf.checkProgram('ocamlyacc', var='OCAMLYACC')

	conf.env['OCAMLC']       = occ
	conf.env['OCAMLOPT']     = opt
	conf.env['OCAMLLEX']     = lex
	conf.env['OCAMLYACC']    = yacc
	conf.env['OCAMLFLAGS']   = ''
	conf.env['OCALINK']      = ''
	conf.env['OCAMLLIB']     = os.popen(conf.env['OCAMLC']+' -where').read().strip()+os.sep
	conf.env['OCALINKFLAGS'] = ''
	return 1

