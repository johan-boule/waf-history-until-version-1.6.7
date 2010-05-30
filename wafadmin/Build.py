#!/usr/bin/env python
# encoding: utf-8
# Thomas Nagy, 2005-2010 (ita)

"""
Dependency tree holder

The class Build holds all the info related to a build:
* file system representation (tree of Node instances)
* various cached objects (task signatures, file scan results, ..)
"""

import os, sys, errno, re, gc, datetime, shutil
try: import cPickle
except: import pickle as cPickle
import Runner, TaskGen, Node, Utils, ConfigSet, Task, Logs, Options, Base, Configure

INSTALL = 1337
"""positive value '->' install"""

UNINSTALL = -1337
"""negative value '<-' uninstall"""

SAVED_ATTRS = 'root node_deps raw_deps task_sigs'.split()
"""Build class members to save"""

CFG_FILES = 'cfg_files'
"""files from the build directory to hash before starting the build"""

class BuildError(Base.WafError):
	"""error raised during the build"""
	def __init__(self, b=None, t=[]):
		self.bld = b
		self.tasks = t
		Base.WafError.__init__(self, self.format_error())

	def format_error(self):
		lst = ['Build failed']
		for tsk in self.tasks:
			txt = tsk.format_error()
			if txt: lst.append(txt)
		return '\n'.join(lst)

class BuildContext(Base.Context):
	"""executes the build"""

	cmd = 'build'
	variant = ''

	def __init__(self, *k, **kw):
		super(BuildContext, self).__init__(kw.get('start', None))

		self.top_dir = kw.get('top_dir', Options.top_dir)

		# output directory - may be set until the nodes are considered
		self.out_dir = kw.get('out_dir', Options.out_dir)

		self.variant_dir = kw.get('variant_dir', self.out_dir)

		self.variant = kw.get('variant', None)
		if self.variant:
			self.variant_dir = os.path.join(self.out_dir, self.variant)

		self.cache_dir = kw.get('cache_dir', None)
		if not self.cache_dir:
			self.cache_dir = self.out_dir + os.sep + Configure.CACHE_DIR

		# bind the build context to the nodes in use
		# this means better encapsulation and no build context singleton
		class node_class(Node.Node):
			pass
		self.node_class = node_class
		self.node_class.__module__ = "Node"
		self.node_class.__name__ = "Nod3"
		self.node_class.bld = self

		# map names to environments, the 'default' must be defined
		self.all_envs = {}

		# ======================================= #
		# code for reading the scripts

		# the current directory from which the code is run
		# the folder changes everytime a wscript is read
		self.path = None

		# nodes
		self.root = None

		# ======================================= #
		# cache variables

		for v in 'task_sigs node_deps raw_deps'.split():
			setattr(self, v, {})

		# list of folders that are already scanned
		# so that we do not need to stat them one more time
		self.cache_dir_contents = {}

		self.task_gen_cache_names = {}
		self.log = None

		self.targets = Options.options.targets
		self.files = Options.options.files

		############ stuff below has not been reviewed

		# Manual dependencies.
		self.deps_man = Utils.defaultdict(list)

		self.tasks_done = []

		# just the structure here
		self.current_group = 0
		self.groups = []
		self.group_names = {}


	def __call__(self, *k, **kw):
		"""Creates a task generator"""
		kw['bld'] = self
		ret = TaskGen.task_gen(*k, **kw)
		self.task_gen_cache_names = {} # reset the cache, each time
		self.add_to_group(ret, group=kw.get('group', None))
		return ret

	def __copy__(self):
		"""Build context copies are not allowed"""
		raise Base.WafError('build contexts are not supposed to be copied')

	def load_envs(self):
		"""load the data from the project directory into self.allenvs"""
		try:
			lst = Utils.listdir(self.cache_dir)
		except OSError as e:
			if e.errno == errno.ENOENT:
				raise Base.WafError('The project was not configured: run "waf configure" first!')
			else:
				raise

		if not lst:
			raise Base.WafError('The cache directory is empty: reconfigure the project')

		for fname in lst:
			if fname.endswith(Configure.CACHE_SUFFIX):
				env = ConfigSet.ConfigSet(os.path.join(self.cache_dir, fname))
				name = fname[:-len(Configure.CACHE_SUFFIX)]
				self.all_envs[name] = env

				for f in env[CFG_FILES]:
					newnode = self.path.find_or_declare(f)
					try:
						h = Utils.h_file(newnode.abspath())
					except (IOError, AttributeError):
						Logs.error('cannot find %r' % f)
						h = Utils.SIG_NIL
					newnode.sig = h

	def make_root(self):
		"""Creates a node representing the filesystem root"""
		Node.Nod3 = self.node_class
		self.root = Node.Nod3('', None)

	def init_dirs(self, src, bld):
		"""Initializes the project directory and the build directory"""
		if not self.root:
			self.make_root()
		self.path = self.srcnode = self.root.find_dir(src)
		self.bldnode = self.root.make_node(bld)
		self.bldnode.mkdir()
		self.variant_dir = self.bldnode.abspath()
		if self.variant:
			self.variant_dir += os.sep + self.variant

		# TODO to cache or not to cache?
		self.bld2src = {id(self.bldnode): self.srcnode}
		self.src2bld = {id(self.srcnode): self.bldnode}

	def prepare(self):
		"""see Context.prepare"""
		self.load()

		self.init_dirs(self.top_dir, self.variant_dir)

		if not self.all_envs:
			self.load_envs()

	def run_user_code(self):
		"""Overridden from Base.Context"""
		self.execute_build()

	def execute_build(self):
		"""Executes the build, it is shared by install and uninstall"""

		self.recurse(self.curdir)
		self.pre_build()
		self.flush()
		try:
			self.compile()
		finally:
			if Options.options.progress_bar: print('')
			Logs.info("Waf: Leaving directory `%s'" % self.out_dir)
		self.post_build()

	def load(self):
		"Loads the cache from the disk (pickle)"
		try:
			env = ConfigSet.ConfigSet(os.path.join(self.cache_dir, 'build.config.py'))
		except (IOError, OSError):
			pass
		else:
			if env['version'] < Base.HEXVERSION:
				raise Base.WafError('Version mismatch! reconfigure the project')
			for t in env['tools']:
				self.setup(**t)

		try:
			gc.disable()
			f = data = None

			Node.Nod3 = self.node_class

			try:
				f = open(os.path.join(self.variant_dir, Base.DBFILE), 'rb')
			except (IOError, EOFError):
				# handle missing file/empty file
				pass

			if f:
				data = cPickle.load(f)
				for x in SAVED_ATTRS:
					setattr(self, x, data[x])
			else:
				Logs.debug('build: Build cache loading failed')

		finally:
			if f: f.close()
			gc.enable()

	def save(self):
		"Stores the cache on disk (pickle), see self.load"
		gc.disable()
		self.root.__class__.bld = None

		# some people are very nervous with ctrl+c so we have to make a temporary file
		Node.Nod3 = self.node_class
		db = os.path.join(self.variant_dir, Base.DBFILE)
		file = open(db + '.tmp', 'wb')
		data = {}
		for x in SAVED_ATTRS: data[x] = getattr(self, x)
		cPickle.dump(data, file)
		file.close()

		# do not use shutil.move
		try: os.unlink(db)
		except OSError: pass
		os.rename(db + '.tmp', db)
		self.root.__class__.bld = self
		gc.enable()

	# ======================================= #

	def compile(self):
		"""The cache file is not written if nothing was build at all (build is up to date)"""
		Logs.debug('build: compile called')

		def dw(on=True):
			if Options.options.progress_bar:
				if on: sys.stderr.write(Logs.colors.cursor_on)
				else: sys.stderr.write(Logs.colors.cursor_off)

		Logs.debug('build: executor starting')

		# use another object to perform the producer-consumer logic (reduce the complexity)
		self.generator = Runner.Parallel(self)
		self.generator.biter = self.get_build_iterator()
		dw(on=False)

		try:
			self.generator.start() # vroom
		except KeyboardInterrupt:
			dw()
			#if Runner.TaskConsumer.consumers:
			# TODO optimize
			self.save()
			raise
		except Exception:
			dw()
			# do not store anything, for something bad happened
			raise
		else:
			dw()
			#if self.: TODO speed up the no-op build here
			self.save()

		if self.generator.error:
			raise BuildError(self, self.generator.error)

	def setup(self, tool, tooldir=None, funs=None):
		"""Loads the waf tools used during the build (task classes, etc)"""
		if isinstance(tool, list):
			for i in tool: self.setup(i, tooldir)
			return

		module = Base.load_tool(tool, tooldir)
		if hasattr(module, "setup"): module.setup(self)

	def get_env(self):
		return self.env_of_name('default')
	def set_env(self, name, val):
		self.all_envs[name] = val

	env = property(get_env, set_env)

	def env_of_name(self, name):
		"""Configuration data access"""
		try:
			return self.all_envs[name]
		except KeyError:
			Logs.error('no such environment: '+name)
			return None


	def add_manual_dependency(self, path, value):
		"""Adds a dependency from a node object to a path (string or node)"""
		if isinstance(path, Node.Node):
			node = path
		elif os.path.isabs(path):
			node = self.root.find_resource(path)
		else:
			node = self.path.find_resource(path)
		self.deps_man[id(node)].append(value)

	def launch_node(self):
		"""returns the launch directory as a node object"""
		try:
			# private cache
			return self.p_ln
		except AttributeError:
			self.p_ln = self.root.find_dir(Options.launch_dir)
			return self.p_ln

	## the following methods are candidates for the stable apis ##

	def hash_env_vars(self, env, vars_lst):
		"""hash environment variables
		['CXX', ..] -> [env['CXX'], ..] -> md5()

		cached by build context
		"""

		# ccroot objects use the same environment for building the .o at once
		# the same environment and the same variables are used

		if not env.table:
			env = env.parent
			if not env:
				return Utils.SIG_NIL

		idx = str(id(env)) + str(vars_lst)
		try:
			cache = self.cache_env
		except AttributeError:
			cache = self.cache_env = {}
		else:
			try:
				return self.cache_env[idx]
			except KeyError:
				pass

		lst = [str(env[a]) for a in vars_lst]
		ret = Utils.h_list(lst)
		Logs.debug('envhash: %r %r', ret, lst)

		cache[idx] = ret

		return ret

	def get_tgen_by_name(self, name):
		"""Retrieves a task generator from its name or its target name
		the name must be unique"""
		cache = self.task_gen_cache_names
		if not cache:

			# create the index lazily
			for g in self.groups:
				for tg in g:
					try:
						if tg.name:
							cache[tg.name] = tg
						else:
							if isinstance(tg.target, str):
								target = tg.target
							else:
								target = ' '.join(tg.target)
							if not cache.get(target, None):
								cache[target] = tg
					except AttributeError:
						# raised if not a task generator, which should be uncommon
						pass
		try:
			return cache[name]
		except KeyError:
			raise Base.WafError('Could not find a task generator for the name %r' % name)

	def flush(self):
		"""tell the task generators to create the tasks"""

		# setting the timer here looks weird
		self.timer = Utils.Timer()

		# force the initialization of the mapping name->object in flush
		# get_tgen_by_name can be used in userland scripts, in that case beware of incomplete mapping
		self.task_gen_cache_names = {}

		Logs.debug('build: delayed operation TaskGen.flush() called')

		if self.targets:
			Logs.debug('task_gen: posting task generators %r', self.targets)

			to_post = []
			min_grp = 0
			for name in self.targets.split(','):
				tg = self.get_tgen_by_name(name)

				if not tg:
					raise Base.WafError('target %r does not exist' % name)

				m = self.get_group_idx(tg)
				if m > min_grp:
					min_grp = m
					to_post = [tg]
				elif m == min_grp:
					to_post.append(tg)

			Logs.debug('group: Forcing up to group %s for target %s', self.get_group_name(min_grp), self.targets)

			# post all the task generators in previous groups
			for i in xrange(len(self.groups)):
				if i == min_grp:
					break
				g = self.groups[i]
				Logs.debug('group: Forcing group %s', self.get_group_name(g))
				for tg in g:
					if isinstance(tg, TaskGen.task_gen):
						Logs.debug('group: Posting %s', tg.name or tg.target)
						tg.post()

			# then post the task generators listed in options.targets in the last group
			for tg in to_post:
				tg.post()

		else:
			Logs.debug('task_gen: posting task generators (normal)')
			for g in self.groups:
				for tg in g:
					if isinstance(tg, TaskGen.task_gen):
						Logs.debug('group: Posting %s', tg.name or tg.target)
						tg.post()

	def progress_line(self, state, total, col1, col2):
		"""Compute the progress bar"""
		n = len(str(total))

		Utils.rot_idx += 1
		ind = Utils.rot_chr[Utils.rot_idx % 4]

		pc = (100.*state)/total
		eta = str(self.timer)
		fs = "[%%%dd/%%%dd][%%s%%2d%%%%%%s][%s][" % (n, n, ind)
		left = fs % (state, total, col1, pc, col2)
		right = '][%s%s%s]' % (col1, eta, col2)

		cols = Logs.get_term_cols() - len(left) - len(right) + 2*len(col1) + 2*len(col2)
		if cols < 7: cols = 7

		ratio = int((cols*state)/total) - 1

		bar = ('='*ratio+'>').ljust(cols)
		msg = Utils.indicator % (left, bar, right)

		return msg

	def exec_command(self, cmd, **kw):
		"""'runner' zone is printed out for waf -v, see wafadmin/Options.py"""
		Logs.debug('runner: system command -> %s' % cmd)
		if self.log:
			self.log.write('%s\n' % cmd)
			kw['log'] = self.log

		# ensure that a command is always frun from somewhere
		try:
			if not kw.get('cwd', None):
				kw['cwd'] = self.cwd
		except AttributeError:
			self.cwd = kw['cwd'] = self.variant_dir

		return Utils.exec_command(cmd, **kw)

	def printout(self, s):
		"""for printing stuff TODO remove?"""
		f = self.log or sys.stderr
		f.write(s)
		#f.flush()

	def pre_recurse(self, name_or_mod, path, nexdir):
		"""from the context class"""
		if not hasattr(self, 'oldpath'):
			self.oldpath = []
		self.oldpath.append(self.path)
		self.path = self.root.find_dir(nexdir)
		return {'bld': self, 'ctx': self}

	def post_recurse(self, name_or_mod, path, nexdir):
		"""from the context class"""
		self.path = self.oldpath.pop()

	def pre_build(self):
		"""executes the user-defined methods before the build starts"""
		if hasattr(self, 'pre_funs'):
			for m in self.pre_funs:
				m(self)

	def post_build(self):
		"""executes the user-defined methods after the build is complete (no execution when the build fails)"""
		if hasattr(self, 'post_funs'):
			for m in self.post_funs:
				m(self)

	def add_pre_fun(self, meth):
		"""binds a method to be executed after the scripts are read and before the build starts"""
		try: self.pre_funs.append(meth)
		except AttributeError: self.pre_funs = [meth]

	def add_post_fun(self, meth):
		"""binds a method to be executed immediately after the build is complete"""
		try: self.post_funs.append(meth)
		except AttributeError: self.post_funs = [meth]

	def get_group(self, x):
		"""get the group x (name or number), or the current group"""
		if not self.groups:
			self.add_group()
		if x is None:
			return self.groups[self.current_group]
		if x in self.group_names:
			return self.group_names[x]
		return self.groups[x]

	def add_to_group(self, tgen, group=None):
		"""add a task or a task generator for the build"""
		# paranoid
		assert(isinstance(tgen, TaskGen.task_gen) or isinstance(tgen, Task.TaskBase))
		self.get_group(group).append(tgen)

	def get_group_name(self, g):
		"""name for the group g (utility)"""
		if not isinstance(g, BuildGroup):
			g = self.groups[g]
		for x in self.group_names:
			if id(self.group_names[x]) == id(g):
				return x
		return ''

	def get_group_idx(self, tg):
		"""group the task generator tg belongs to, used by flush() for --target=xyz"""
		se = id(tg)
		for i in range(len(self.groups)):
			for t in self.groups[i]:
				if id(t) == se:
					return i
		return None

	def add_group(self, name=None, move=True):
		"""add a new group of tasks/task generators"""
		#if self.groups and not self.groups[0].tasks:
		#	error('add_group: an empty group is already present')
		if name and name in self.group_names:
			Logs.error('add_group: name %s already present' % name)
		g = []
		self.group_names[name] = g
		self.groups.append(g)
		if move:
			self.current_group = len(self.groups) - 1

	def set_group(self, idx):
		"""set the current group to be idx: now new task generators will be added to this group by default"""
		if isinstance(idx, str):
			g = self.groups_names[idx]
			for i in range(len(self.groups)):
				if id(g) == id(self.groups[i]):
					self.current_group = i
		else:
			self.current_group = idx

	def total(self):
		"""total of tasks"""
		total = 0
		for group in self.groups:
			for tg in group:
				try:
					total += len(tg.tasks)
				except AttributeError:
					total += 1
		return total

	def get_build_iterator(self):
		"""creates a generator object that returns tasks executable in parallel"""
		self.cur = 0
		while self.cur < len(self.groups):
			tasks = []
			for tg in self.groups[self.cur]:
				# TODO a try-except might be more efficient
				if isinstance(tg, Task.TaskBase):
					tasks.append(tg)
				else:
					tasks.extend(tg.tasks)

			# if the constraints are set properly (ext_in/ext_out, before/after)
			# the call to set_file_constraints may be removed (can be a 15% penalty on no-op rebuilds)
			#
			# the tasks are split into groups of independent tasks that may be parallelized
			# and a topological sort is performed
			#
			# if the tasks have only files, set_file_constraints is required but extract_constraints is not necessary
			#
			Task.set_file_constraints(tasks)

			# use the after/before + ext_out/ext_in to perform a topological sort
			cstr_groups = Utils.defaultdict(list)
			cstr_order = Utils.defaultdict(set)
			for x in tasks:
				h = x.hash_constraints()
				cstr_groups[h].append(x)

			keys = list(cstr_groups.keys())
			maxi = len(keys)

			# this list should be short
			for i in range(maxi):
				t1 = cstr_groups[keys[i]][0]
				for j in range(i + 1, maxi):
					t2 = cstr_groups[keys[j]][0]

					# add the constraints based on the comparisons
					val = (Task.compare_exts(t1, t2) or Task.compare_partial(t1, t2))
					if val > 0:
						cstr_order[keys[i]].add(keys[j])
					elif val < 0:
						cstr_order[keys[j]].add(keys[i])

			while 1:
				unconnected = []
				remainder = []

				for u in keys:
					for k in cstr_order.values():
						if u in k:
							remainder.append(u)
							break
					else:
						unconnected.append(u)

				toreturn = []
				for y in unconnected:
					toreturn.extend(cstr_groups[y])

				# remove stuff only after
				for y in unconnected:
					try: cstr_order.__delitem__(y)
					except KeyError: pass
					cstr_groups.__delitem__(y)

				if not toreturn:
					if remainder:
						raise Base.WafError("Circular order constraint detected %r" % remainder)
					self.cur += 1
					break

				yield toreturn
		while 1:
			yield []

	def install_files(self, *k, **kw):
		pass

	def install_as(self, *k, **kw):
		pass

	def symlink_as(self, *k, **kw):
		pass

def check_dir(dir):
	"""
	Ensure that a directory exists. Equivalent to mkdir -p.
	@type  dir: string
	@param dir: Path to directory
	"""
	try:
		os.stat(dir)
	except OSError:
		try:
			os.makedirs(dir)
		except OSError as e:
			raise Base.WafError('Cannot create folder %r (original error: %r)' % (dir, e))

def group_method(fun):
	"""
	sets a build context method to execute after the current group has finished executing
	this is useful for installing build files:
	* calling install_files/install_as will fail if called too early
	* people do not want to define install method in their task classes
	"""
	def f(*k, **kw):
		if not k[0].is_install:
			return False

		postpone = True
		if 'postpone' in kw:
			postpone = kw['postpone']
			del kw['postpone']

		if postpone:
			if not self.groups: self.add_group()
			self.groups[self.current_group].post_funs.append((fun, k, kw))
			kw['cwd'] = k[0].path
		else:
			fun(*k, **kw)
	return f

class InstallContext(BuildContext):
	"""installs the targets on the system"""
	cmd = 'install'

	def __init__(self, start=None):
		super(InstallContext, self).__init__(start)

		# list of targets to uninstall for removing the empty folders after uninstalling
		self.uninstall = []

		self.is_install = INSTALL

	def run_user_code(self):
		"""see Context.run_user_code"""
		self.is_install = INSTALL
		self.execute_build()
		self.install()

	def do_install(self, src, tgt, chmod=Utils.O644):
		"""returns true if the file was effectively installed or uninstalled, false otherwise"""
		if self.is_install > 0:
			if not Options.options.force:
				# check if the file is already there to avoid a copy
				try:
					st1 = os.stat(tgt)
					st2 = os.stat(src)
				except OSError:
					pass
				else:
					# same size and identical timestamps -> make no copy
					if st1.st_mtime >= st2.st_mtime and st1.st_size == st2.st_size:
						return False

			srclbl = src.replace(self.srcnode.abspath()+os.sep, '')
			Logs.info("* installing %s as %s" % (srclbl, tgt))

			# following is for shared libs and stale inodes (-_-)
			try: os.remove(tgt)
			except OSError: pass

			try:
				shutil.copy2(src, tgt)
				os.chmod(tgt, chmod)
			except IOError:
				try:
					os.stat(src)
				except (OSError, IOError):
					Logs.error('File %r does not exist' % src)
				raise Base.WafError('Could not install the file %r' % tgt)
			return True

		elif self.is_install < 0:
			Logs.info("* uninstalling %s" % tgt)

			self.uninstall.append(tgt)

			try:
				os.remove(tgt)
			except OSError as e:
				if e.errno != errno.ENOENT:
					if not getattr(self, 'uninstall_error', None):
						self.uninstall_error = True
						Logs.warn('build: some files could not be uninstalled (retry with -vv to list them)')
					if Logs.verbose > 1:
						Logs.warn('could not remove %s (error code %r)' % (e.filename, e.errno))
			return True

	def get_install_path(self, path, env=None):
		"installation path prefixed by the destdir, the variables like in '${PREFIX}/bin' are substituted"
		if not env: env = self.env
		destdir = Options.options.destdir
		path = path.replace('/', os.sep)
		destpath = Utils.subst_vars(path, env)
		if destdir:
			destpath = os.path.join(destdir, destpath.lstrip(os.sep))
		return destpath

	def install(self):
		"""Called for both install and uninstall"""
		Logs.debug('build: install called')

		self.flush()

		# remove empty folders after uninstalling
		if self.is_install < 0:
			lst = []
			for x in self.uninstall:
				dir = os.path.dirname(x)
				if not dir in lst: lst.append(dir)
			lst.sort()
			lst.reverse()

			nlst = []
			for y in lst:
				x = y
				while len(x) > 4:
					if not x in nlst: nlst.append(x)
					x = os.path.dirname(x)

			nlst.sort()
			nlst.reverse()
			for x in nlst:
				try: os.rmdir(x)
				except OSError: pass

	def install_files(self, path, files, env=None, chmod=Utils.O644, relative_trick=False, cwd=None):
		"""To install files only after they have been built, put the calls in a method named
		post_build on the top-level wscript

		The files must be a list and contain paths as strings or as Nodes

		The relative_trick flag can be set to install folders, use bld.path.ant_glob() with it
		"""
		if env:
			assert isinstance(env, ConfigSet.ConfigSet), "invalid parameter"
		else:
			env = self.env

		if not path: return []

		if not cwd:
			cwd = self.path

		lst = Utils.to_list(files)

		if not getattr(lst, '__iter__', False):
			lst = [lst]

		destpath = self.get_install_path(path, env)

		check_dir(destpath)

		installed_files = []
		for filename in lst:
			if isinstance(filename, str) and os.path.isabs(filename):
				alst = Utils.split_path(filename)
				destfile = os.path.join(destpath, alst[-1])
			else:
				if isinstance(filename, Node.Node):
					nd = filename
				else:
					nd = cwd.find_resource(filename)
				if not nd:
					raise Base.WafError("Unable to install the file %r (not found in %s)" % (filename, cwd))

				if relative_trick:
					destfile = os.path.join(destpath, filename)
					check_dir(os.path.dirname(destfile))
				else:
					destfile = os.path.join(destpath, nd.name)

				filename = nd.abspath()

			if self.do_install(filename, destfile, chmod):
				installed_files.append(destfile)
		return installed_files

	def install_as(self, path, srcfile, env=None, chmod=Utils.O644, cwd=None):
		"""
		srcfile may be a string or a Node representing the file to install

		returns True if the file was effectively installed, False otherwise
		"""
		if env:
			assert isinstance(env, ConfigSet.ConfigSet), "invalid parameter"
		else:
			env = self.env

		if not path:
			raise Base.WafError("where do you want to install %r? (%r?)" % (srcfile, path))

		if not cwd:
			cwd = self.path

		destpath = self.get_install_path(path, env)

		dir, name = os.path.split(destpath)
		check_dir(dir)

		# the source path
		if isinstance(srcfile, Node.Node):
			src = srcfile.abspath()
		else:
			src = srcfile
			if not os.path.isabs(srcfile):
				node = cwd.find_resource(srcfile)
				if not node:
					raise Base.WafError("Unable to install the file %r (not found in %s)" % (srcfile, cwd))
				src = node.abspath()

		return self.do_install(src, destpath, chmod)

	def symlink_as(self, path, src, env=None, cwd=None):
		"""example:  bld.symlink_as('${PREFIX}/lib/libfoo.so', 'libfoo.so.1.2.3') """

		if sys.platform == 'win32':
			# well, this *cannot* work
			return

		if not path:
			raise Base.WafError("where do you want to install %r? (%r?)" % (src, path))

		tgt = self.get_install_path(path, env)

		dir, name = os.path.split(tgt)
		check_dir(dir)

		if self.is_install > 0:
			link = False
			if not os.path.islink(tgt):
				link = True
			elif os.readlink(tgt) != src:
				link = True

			if link:
				try: os.remove(tgt)
				except OSError: pass
				Logs.info('* symlink %s (-> %s)' % (tgt, src))
				os.symlink(src, tgt)
			return 0

		else: # UNINSTALL
			try:
				Logs.info('* removing %s' % (tgt))
				os.remove(tgt)
				return 0
			except OSError:
				return 1

	install_as = group_method(install_as)
	install_files = group_method(install_files)
	symlink_as = group_method(symlink_as)


class UninstallContext(InstallContext):
	"""removes the targets installed"""
	cmd = 'uninstall'
	def run_user_code(self):
		"""see Context.run_user_code"""
		self.is_install = UNINSTALL

		try:
			# do not execute any tasks
			def runnable_status(self):
				return SKIP_ME
			setattr(Task.Task, 'runnable_status_back', Task.Task.runnable_status)
			setattr(Task.Task, 'runnable_status', runnable_status)
			self.execute_build()
			self.install()
		finally:
			setattr(Task.Task, 'runnable_status', Task.Task.runnable_status_back)

class CleanContext(BuildContext):
	"""cleans the project"""
	cmd = 'clean'
	def run_user_code(self):
		"""see Context.run_user_code"""
		self.recurse(self.curdir)
		try:
			self.clean()
		finally:
			self.save()

	def clean(self):
		Logs.debug('build: clean called')

		# TODO clean could remove the files except the ones listed in env[CFG_FILES]

		# forget about all the nodes
		self.root.children = {}

		for v in 'node_deps task_sigs raw_deps'.split():
			setattr(self, v, {})

class ListContext(BuildContext):
	"""lists the targets to execute"""

	cmd = 'list'
	def run_user_code(self):
		"""see Context.run_user_code"""
		self.recurse(self.curdir)
		self.pre_build()
		self.flush()
		try:
			# force the cache initialization
			self.get_tgen_by_name('')
		except:
			pass
		lst = list(self.task_gen_cache_names.keys())
		lst.sort()
		for k in lst:
			Logs.pprint('GREEN', k)

