
import TaskGen
from TaskGen import feature, after, before
from ccroot import get_target_name

from Constants import SKIP_ME
import Task

cc = Task.TaskBase.classes['cc_link']
class inst_cc(cc):
	def runnable_status(self):
		if not self.generator.bld.is_install:
			return SKIP_ME
		return Task.Task.runnable_status(self)

old = TaskGen.task_gen.apply_link

@feature('cprogram', 'cshlib', 'cstaticlib')
@after('apply_core')
def apply_link(self):
	link = getattr(self, 'link', None)

	if link and link != 'cc_link':
		return old(self)

	rpath = get_target_name(self)
	target = rpath.replace('.so', '_.so')

	tsk = self.create_task('inst_cc')
	outputs = [t.outputs[0] for t in self.compiled_tasks]
	tsk.set_inputs(outputs)
	tsk.set_outputs(self.path.find_or_declare(target))

	rp = self.create_task('cc_link')
	rp.inputs = tsk.inputs
	rp.set_outputs(self.path.find_or_declare(rpath))
	rp.set_run_after(tsk)
	rp.env = tsk.env.copy()
	self.rpath_task = rp

	self.link_task = tsk

@feature('cprogram', 'cshlib', 'cstaticlib')
@after('apply_link')
@before('apply_obj_vars')
def evil_rpath(self):
	rp = self.rpath_task

	# rpath flag mess
	rpath_st = rp.env['RPATH_ST']
	app = rp.env.append_unique
	for i in rp.env['RPATH']:
		if i and rpath_st:
			app('LINKFLAGS', rpath_st % i)

	self.env['RPATH'] = []

