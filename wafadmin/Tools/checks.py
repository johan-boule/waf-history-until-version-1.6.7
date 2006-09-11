#! /usr/bin/env python
# encoding: utf-8
# Thomas Nagy, 2006 (ita)

import Utils
from Params import error

endian_str = """
#include <stdio.h>
int am_big_endian()
{
        long one = 1;
        return !(*((char *)(&one)));
}

int main()
{
  if (am_big_endian())
     printf("bigendian=1\\n");
  else
     printf("bigendian=0\\n");

  return 0;
}
"""

def checkEndian(self, define='', pathlst=[]):
	if define == '': define = 'IS_BIGENDIAN'

	if self.isDefined(define): return self.getDefine(define)

	global endian

	test = self.create_test_configurator()
	test.code = endian_str
	code = test.run()['result']

	#code = self.TryRun(endian_str, pathlst=pathlst)

	try:
		t = Utils.to_hashtable(code)
		is_big = int(t['bigendian'])
	except:
		error('endian test failed '+code)
		is_big = 0
		raise

	if is_big: strbig = 'big endian'
	else:      strbig = 'little endian'

	self.checkMessageCustom('endianness', '', strbig)
	self.addDefine(define, is_big)
	return is_big

features_str = """
#include <stdio.h>
int am_big_endian()
{
        long one = 1;
        return !(*((char *)(&one)));
}

int main()
{
  if (am_big_endian())
     printf("bigendian=1\\n");
  else
     printf("bigendian=0\\n");

  printf("int_size=%d\\n", sizeof(int));
  printf("long_int_size=%d\\n", sizeof(long int));
  printf("long_long_int_size=%d\\n", sizeof(long long int));
  printf("double_size=%d\\n", sizeof(double));

  return 0;
}
"""

def checkFeatures(self, lst=[], pathlst=[]):

	global endian

	test = self.create_test_configurator()
	test.code = features_str
	code = test.run()['result']
	#code = self.TryRun(features_str, pathlst=pathlst)

	try:
		t = Utils.to_hashtable(code)
		is_big = int(t['bigendian'])
	except:
		error('endian test failed '+code)
		is_big = 0
		raise

	if is_big: strbig = 'big endian'
	else:      strbig = 'little endian'


	self.checkMessageCustom('endianness', '', strbig)

	self.checkMessageCustom('int size', '', t['int_size'])
	self.checkMessageCustom('long int size', '', t['long_int_size'])
	self.checkMessageCustom('long long int size', '', t['long_long_int_size'])
	self.checkMessageCustom('double size', '', t['double_size'])

	self.addDefine('IS_BIGENDIAN', is_big)
	self.addDefine('INT_SIZE', int(t['int_size']))
	self.addDefine('LONG_INT_SIZE', int(t['long_int_size']))
	self.addDefine('LONG_LONG_INT_SIZE', int(t['long_long_int_size']))
	self.addDefine('DOUBLE_SIZE', int(t['double_size']))

	return is_big

def check_header(self, header, define=''):

	if not define:
		upstr = header.upper().replace('/', '_').replace('.', '_')
		define = 'HAVE_' + upstr

	test = self.create_header_configurator()
	test.name = header
	test.define = define
	return test.run()

def try_build_and_exec(self, code, uselib=''):
	test = self.create_test_configurator()
	test.uselib = uselib
        test.code = code
	ret = test.run()
	if ret: return ret['result']
	return None

def check_flags(self, flags, uselib='', options='', msg=1):
	test = self.create_test_configurator()
	test.uselib = uselib
        test.code = 'int main() {return 0;}\n'
	test.flags = flags
	ret = test.run()

	if msg: self.checkMessage('flags', flags, not (ret is None))

	if ret: return 1
	return None

def setup(env):
	# we provide no new action or builder
	pass

def detect(conf):
	# attach the checks to the conf object
	conf.hook(checkEndian)
	conf.hook(checkFeatures)
	conf.hook(check_header)
	conf.hook(try_build_and_exec)
	conf.hook(check_flags)
	return 1

