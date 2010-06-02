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
from wafadmin import Runner, TaskGen, Utils, ConfigSet, Task, Logs, Options, Context, Configure, Errors
import wafadmin.Node

INSTALL = 1337
"""positive value '->' install"""

UNINSTALL = -1337
"""negative value '<-' uninstall"""

SAVED_ATTRS = 'root node_deps raw_deps task_sigs'.split()
"""Build class members to save"""

CFG_FILES = 'cfg_files'
"""files from the build directory to hash before starting the build"""

class BuildContext(Context.Context):
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

		# map names to environments, the 'default' must be defined
		self.all_envs = {}

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
		self.launch_dir = Options.launch_dir

		############ stuff below has not been reviewed

		# Manual dependencies.
		self.deps_man = Utils.defaultdict(list)

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
		raise Errors.WafError('build contexts are not supposed to be copied')

	def load_envs(self):
		"""load the data from the project directory into self.allenvs"""
		try:
			lst = Utils.listdir(self.cache_dir)
		except OSError as e:
			if e.errno == errno.ENOENT:
				raise Errors.WafError('The project was not configured: run "waf configure" first!')
			else:
				raise

		if not lst:
			raise Errors.WafError('The cache directory is empty: reconfigure the project')

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

	def init_dirs(self, src, bld):
		"""Initializes the project directory and the build directory"""
		if not self.root:
			wafadmin.Node.Nod3 = self.node_class
			self.root = wafadmin.Node.Nod3('', None)
		self.path = self.srcnode = self.root.find_dir(src)
		self.bldnode = self.root.make_node(bld)
		self.bldnode.mkdir()
		self.variant_dir = self.bldnode.abspath()
		if self.variant:
			self.variant_dir += os.sep + self.variant

		# TODO to cache or not to cache?
		self.bld2src = {id(self.bldnode): self.srcnode}
		self.src2bld = {id(self.srcnode): self.bldnode}

	def execute(self):
		"""see Context.execute"""
		self.load()
		self.init_dirs(self.top_dir, self.variant_dir)
		if not self.all_envs:
			self.load_envs()

		self.execute_build()

	def execute_build(self):
		"""Executes the build, it is shared by install and uninstall"""

		self.recurse(self.path.abspath())
		self.pre_build()
		self.flush()
		if Options.options.progress_bar:
			sys.stderr.write(Logs.colors.cursor_off)
		try:
			self.compile()
		finally:
			if Options.options.progress_bar:
				sys.stderr.write(Logs.colors.cursor_on)
				print('')
			Logs.info("Waf: Leaving directory `%s'" % self.out_dir)
		self.post_build()

	def load(self):
		"Loads the cache from the disk (pickle)"
		try:
			env = ConfigSet.ConfigSet(os.path.join(self.cache_dir, 'build.config.py'))
		except (IOError, OSError):
			pass
		else:
			if env['version'] < Context.HEXVERSION:
				raise Errors.WafError('Version mismatch! reconfigure the project')
			for t in env['tools']:
				self.setup(**t)

		try:
			gc.disable()
			f = data = None

			wafadmin.Node.Nod3 = self.node_class

			try:
				f = open(os.path.join(self.variant_dir, Context.DBFILE), 'rb')
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
		wafadmin.Node.Nod3 = self.node_class
		db = os.path.join(self.variant_dir, Context.DBFILE)
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
		Logs.debug('build: compile()')

		# use another object to perform the producer-consumer logic (reduce the complexity)
		self.parallel = Runner.Parallel(self)
		self.parallel.biter = self.get_build_iterator()
		try:
			self.parallel.start() # vroom
		except KeyboardInterrupt:
			self.save()
			raise
		else:
			self.save()

		if self.parallel.error:
			raise Errors.BuildError(self.parallel.error)

	def setup(self, tool, tooldir=None, funs=None):
		"""Loads the waf tools used during the build (task classes, etc)"""
		if isinstance(tool, list):
			for i in tool: self.setup(i, tooldir)
			return

		module = Context.load_tool(tool, tooldir)
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
		if isinstance(path, wafadmin.Node.Node):
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
			self.p_ln = self.root.find_dir(self.launch_dir)
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
						cache[tg.name] = tg
					except AttributeError:
						# raised if not a task generator, which should be uncommon
						pass
		try:
			return cache[name]
		except KeyError:
			raise Errors.WafError('Could not find a task generator for the name %r' % name)

	def flush(self):
		"""tell the task generators to create the tasks"""

		# setting the timer here looks weird
		self.timer = Utils.Timer()

		# force the initialization of the mapping name->object in flush
		# get_tgen_by_name can be used in userland scripts, in that case beware of incomplete mapping
		self.task_gen_cache_names = {}

		Logs.debug('build: delayed operation TaskGen.flush() called')

		if self.targets == '*':
			Logs.debug('task_gen: posting task generators (normal)')
			for g in self.groups:
				for tg in g:
					if isinstance(tg, TaskGen.task_gen):
						Logs.debug('group: Posting %s', tg.name or tg.target)
						tg.post()
		elif self.targets:
			Logs.debug('task_gen: posting task generators %r', self.targets)

			to_post = []
			min_grp = 0
			for name in self.targets.split(','):
				tg = self.get_tgen_by_name(name)

				if not tg:
					raise Errors.WafError('target %r does not exist' % name)

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
			Logs.debug('task_gen: posting task generators (launch directory)')
			ln = self.launch_node()
			for g in self.groups:
				for tg in g:
					if isinstance(tg, TaskGen.task_gen):
						if not tg.path.is_child_of(ln):
							continue
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
		if not isinstance(g, list):
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
						raise Errors.WafError("Circular order constraint detected %r" % remainder)
					self.cur += 1
					break

				yield toreturn
		while 1:
			yield []

	def install_files(self, *k, **kw):
		"""Actual implementation provided by InstallContext and UninstallContext"""
		pass

	def install_as(self, *k, **kw):
		"""Actual implementation provided by InstallContext and UninstallContext"""
		pass

	def symlink_as(self, *k, **kw):
		"""Actual implementation provided by InstallContext and UninstallContext"""
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
			raise Errors.WafError('Cannot create folder %r (original error: %r)' % (dir, e))

class inst_task(Task.Task):
	color = 'CYAN'
	def runnable_status(self):
		buf = []
		for x in Utils.to_list(self.source):
			y = self.path.find_resource(x)
			if not y:
				raise Errors.WafError('could not find %r in %r' % (x, self.path))
			buf.append(y)
		self.set_inputs(buf)
		return Task.RUN_ME

	def __str__(self):
		return self.generator.bld.install_msg

	def run(self):
		return self.generator.exec_task()

	def get_install_path(self):
		"installation path prefixed by the destdir, the variables like in '${PREFIX}/bin' are substituted"
		dest = self.dest.replace('/', os.sep)
		dest = Utils.subst_vars(self.dest, self.env)
		if Options.options.destdir:
			dest = os.path.join(Options.options.destdir, dest.lstrip(os.sep))
		return dest

	def exec_install_files(self):
		destpath = self.get_install_path()
		check_dir(destpath)
		for x in self.inputs:
			self.generator.bld.do_install(x.abspath(), destpath, self.chmod)

	def exec_install_as(self):
		destfile = self.get_install_path()
		destpath, _ = os.path.split(destfile)
		check_dir(destpath)
		self.generator.bld.do_install(self.inputs[0].abspath(), destfile, self.chmod)

	def exec_symlink_as(self):
		destfile = self.get_install_path()
		destpath, _ = os.path.split(destfile)
		check_dir(destpath)

		self.generator.bld.do_link(self.link, destfile)

class InstallContext(BuildContext):
	"""installs the targets on the system"""
	cmd = 'install'

	def __init__(self, start=None):
		super(InstallContext, self).__init__(start)

		# list of targets to uninstall for removing the empty folders after uninstalling
		self.uninstall = []
		self.is_install = INSTALL
		self.install_msg = 'installing...\n'

	def execute(self):
		"""see Context.execute"""
		self.load()
		self.init_dirs(self.top_dir, self.variant_dir)
		if not self.all_envs:
			self.load_envs()

		self.execute_build()

	def do_install(self, src, tgt, chmod=Utils.O644):
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
			raise Errors.WafError('Could not install the file %r' % tgt)

	def do_link(self, src, tgt):
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

	def install_files(self, dest, files, env=None, chmod=Utils.O644, relative_trick=False, cwd=None):
		tsk = inst_task(env=env or self.env)
		tsk.bld = self
		tsk.path = cwd or self.path
		tsk.chmod = chmod
		tsk.source = files
		tsk.dest = dest
		tsk.exec_task = tsk.exec_install_files
		self.add_to_group(tsk)
		return tsk


		installed_files = []
		for filename in lst:
			if isinstance(filename, str) and os.path.isabs(filename):
				alst = Utils.split_path(filename)
				destfile = os.path.join(destpath, alst[-1])
			else:
				if isinstance(filename, wafadmin.Node.Node):
					nd = filename
				else:
					nd = cwd.find_resource(filename)
				if not nd:
					raise Errors.WafError("Unable to install the file %r (not found in %s)" % (filename, cwd))

				if relative_trick:
					destfile = os.path.join(destpath, filename)
					check_dir(os.path.dirname(destfile))
				else:
					destfile = os.path.join(destpath, nd.name)

				filename = nd.abspath()

			if self.do_install(filename, destfile, chmod):
				installed_files.append(destfile)
		return installed_files

	def install_as(self, dest, srcfile, env=None, chmod=Utils.O644, cwd=None):
		"""example: bld.install_as('${PREFIX}/bin', 'myapp', chmod=Utils.O755)"""
		tsk = inst_task(env=env or self.env)
		tsk.bld = self
		tsk.path = cwd or self.path
		tsk.chmod = chmod
		tsk.source = srcfile
		tsk.dest = dest
		tsk.exec_task = tsk.exec_install_as
		self.add_to_group(tsk)
		return tsk

	def symlink_as(self, dest, src, env=None, cwd=None):
		"""example:  bld.symlink_as('${PREFIX}/lib/libfoo.so', 'libfoo.so.1.2.3') """

		if sys.platform == 'win32':
			# symlinks *cannot* work on that platform
			return

		tsk = inst_task(env=env or self.env)
		tsk.bld = self
		tsk.dest = dest
		tsk.path = cwd or self.path
		tsk.source = []
		tsk.link = src
		tsk.exec_task = tsk.exec_symlink_as
		self.add_to_group(tsk)
		return tsk

class UninstallContext(InstallContext):
	"""removes the targets installed"""
	cmd = 'uninstall'

	def __init__(self, start=None):
		super(UninstallContext, self).__init__(start)
		self.is_install = UNINSTALL
		self.install_msg = 'removing...\n'

	def do_install(self, src, tgt, chmod=Utils.O644):
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


		while tgt:
			tgt = os.path.dirname(tgt)
			try:
				os.rmdir(tgt)
			except OSError:
				break

	def do_link(self, src, tgt):
		try:
			Logs.info('* removing %s' % (tgt))
			os.remove(tgt)
		except OSError:
			pass

		# TODO ita refactor this into a post build action to uninstall the folders (optimization)
		while tgt:
			tgt = os.path.dirname(tgt)
			try:
				os.rmdir(tgt)
			except OSError:
				break

	def execute(self):
		"""see Context.execute"""
		try:
			# do not execute any tasks
			def runnable_status(self):
				return Task.SKIP_ME
			setattr(Task.Task, 'runnable_status_back', Task.Task.runnable_status)
			setattr(Task.Task, 'runnable_status', runnable_status)

			super(UninstallContext, self).execute()
		finally:
			setattr(Task.Task, 'runnable_status', Task.Task.runnable_status_back)

class CleanContext(BuildContext):
	"""cleans the project"""
	cmd = 'clean'
	def execute(self):
		"""see Context.execute"""
		self.load()
		self.init_dirs(self.top_dir, self.variant_dir)
		if not self.all_envs:
			self.load_envs()

		self.recurse(self.path.abspath())
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
	def execute(self):
		"""see Context.execute"""
		self.load()
		self.init_dirs(self.top_dir, self.variant_dir)
		if not self.all_envs:
			self.load_envs()

		self.recurse(self.path.abspath())
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

class StepContext(BuildContext):
	"""executes tasks in a step-by-step fashion, for debugging"""
	cmd = 'step'

	def __init__(self, *k, **kw):
		super(StepContext, self).__init__(*k, **kw)
		self.targets = '*' # post all task generators
		self.files = Options.options.files

	def compile(self):
		if not self.files:
			Logs.warn('Add a pattern for the debug build, for example "waf step --files=main.c,app"')
			BuildContext.compile(self)
			return

		for pat in self.files.split(','):
			inn = True
			out = True
			if pat.startswith('in:'):
				out = False
				pat = pat.replace('in:', '')
			elif pat.startswith('out:'):
				inn = False
				pat = pat.replace('out:', '')

			pat = re.compile(pat, re.M)

			for g in self.groups:
				for tg in g:
					if isinstance(tg, Task.TaskBase):
						lst = [tg]
					else:
						lst = tg.tasks
					for tsk in lst:
						do_exec = False
						if inn:
							for node in getattr(tsk, 'inputs', []):
								if pat.search(node.abspath()):
									do_exec = True
									break
						if out and not do_exec:
							for node in getattr(tsk, 'outputs', []):
								if pat.search(node.abspath()):
									do_exec = True
									break

						if do_exec:
							ret = tsk.run()
							Logs.info('%s -> %r' % (str(tsk), ret))

