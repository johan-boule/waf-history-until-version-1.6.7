#! /usr/bin/env python
# encoding: utf-8
# Thomas Nagy, 2005, 2006 (ita)

"""
This script is not a good example:
 * it is complicated
 * it does not build anything, it just exits in the init method

Have a look at demos/cc/wscript instead
For configuration examples: demos/adv/wscript
For a project without subdirectory: demos/python/wscript
"""

VERSION="1.2.0"
APPNAME='waf'
REVISION=''

demos = ['cpp', 'qt4', 'tex', 'ocaml', 'kde3', 'adv', 'cc', 'idl', 'docbook', 'xmlwaf', 'gnome']
zip_types = ['bz2', 'gz']

# exclude these modules
forbidden = [x+'.py' for x in 'Test Weak'.split()]

import Params, Utils, Options, os, sys, base64, shutil, re, random, StringIO

print "------> Executing code from the top-level wscript <-----"

# this function is called before any other for parsing the command-line
def set_options(opt):

	# generate waf
	opt.add_option('--make-waf', action='store_true', default=False,
		help='creates the waf script', dest='waf')

	opt.add_option('--zip-type', action='store', default='bz2',
		help='specify the zip type [Allowed values: %s]' % ' '.join(zip_types), dest='zip')

	opt.add_option('--make-batch', action='store_true', default=False,
		help='creates a waf.bat file that calls the waf script. (this is done automatically on win32 systems)',
		dest='make_batch')

	# those ones are not too interesting
	opt.add_option('--set-version', default='',
		help='set the version number for waf releases (for the maintainer)', dest='setver')

	opt.add_option('--strip', action='store_true', default=False,
		help='Shrink waf (quits 25kb)',
		dest='strip_comments')

def encodeAscii85(s):
	out=[]
	app=out.append
	v=[(0,16777216L),(1,65536),(2,256),(3,1)]
	cnt,r = divmod(len(s),4)
	stop=4*cnt
	p1,p2=s[0:stop],s[stop:]
	for i in range(cnt):
		offset=i*4
		num=0
		for (j,mul) in v: num+=mul*ord(p1[offset+j])
		if num==0: out.append('z')
		else:
			x,e=divmod(num,85)
			x,d=divmod(x,85)
			x,c=divmod(x,85)
			a,b=divmod(x,85)
			app(chr(a+33)+chr(b+33)+chr(c+33)+chr(d+33)+chr(e+33))
	if r>0:
		while len(p2)<4: p2=p2+'\x00'
		num=0
		for (j,mul) in v: num+=mul*ord(p2[j])
		x,e=divmod(num,85)
		x,d=divmod(x,85)
		x,c=divmod(x,85)
		a,b=divmod(x,85)
		end=chr(a+33)+chr(b+33)+chr(c+33)+chr(d+33)+chr(e+33)
		app(end[0:1+r])
	return ''.join(out)

def create_waf():
	print "-> preparing waf"
	mw = 'tmp-waf-'+VERSION

	import tarfile, re

	zipType = Params.g_options.zip.strip().lower()
	if zipType not in zip_types:
		zipType = zip_types[0]

	#open a file as tar.[extension] for writing
	tar = tarfile.open('%s.tar.%s' % (mw, zipType), "w:%s" % zipType)
	tarFiles=[]
	#regexpr for python files
	pyFileExp = re.compile(".*\.py$")
	re_doc_1 = re.compile('^\s*"""([^"]+)"""', re.M)
	re_doc_2 = re.compile('^\s*"([^"]+)"', re.M)
	re_doc_3 = re.compile("^\s*#")

	def sfilter(path):
		f = open(path, "r")
		cnt = f.read()
		f.close()
		if not Params.g_options.strip_comments: return (StringIO.StringIO(cnt), len(cnt))
		cnt = re_doc_1.sub('', cnt)
		cnt = re_doc_2.sub('', cnt)
		lst = cnt.split("\n")
		cnt = []
		for x in lst:
			if x=='# quick test #': break
			cnt.append(x)
		cnt = [x for x in cnt if x and not re_doc_3.match(x)]
		cnt = "\n".join(cnt)
		return (StringIO.StringIO(cnt), len(cnt))

	lst = os.listdir('wafadmin')
	files = [os.path.join('wafadmin', s) for s in lst if pyFileExp.match(s) and not s in forbidden]
	tooldir = os.path.join('wafadmin', 'Tools')
	lst = os.listdir(tooldir)
	files += [os.path.join(tooldir, s) for s in lst if pyFileExp.match(s) and not s in forbidden]
	for x in files:
		tarinfo = tar.gettarinfo(x, x)
		tarinfo.uid=tarinfo.gid=1000
		tarinfo.uname=tarinfo.gname="bozo"
		(code, size) = sfilter(x)
		tarinfo.size = size
		tar.addfile(tarinfo, code)
	tar.close()

	f = open('waf-light', 'rb')
	code1 = f.read()
	f.close()

	# now store the revision unique number in waf
	v = 1000000000
	global REVISION
	REVISION = random.randint(v, 2*v)
	reg = re.compile('^REVISION=(.*)', re.M)
	code1 = reg.sub(r'REVISION="%d"' % REVISION, code1)

	prefix = Params.g_options.prefix
	# if the prefix is the default, let's be nice and be platform-independent
	# just in case the created waf is used on either windows or unix
	if prefix == Options.default_prefix:
		prefix = "sys.platform=='win32' and 'c:/temp' or '/usr/local'"
	else:
		prefix = '"%s"' % prefix #encase in quotes

	reg = re.compile('^INSTALL=(.*)', re.M)
	code1 = reg.sub(r'INSTALL=%s' % prefix, code1)
	#change the tarfile extension in the waf script
	reg = re.compile('bz2', re.M)
	code1 = reg.sub(zipType, code1)

	f = open('%s.tar.%s' % (mw, zipType), 'rb')
	cnt = f.read()
	f.close()
	code2 = encodeAscii85(cnt)
	f = open('waf', 'wb')
	f.write(code1)
	f.write('# ===>BEGIN WOOF<===\n')
	f.write('#')
	f.write(code2)
	f.write('\n')
	f.write('# ===>END WOOF<===\n')
	f.close()

	if sys.platform == 'win32' or Params.g_options.make_batch:
		f = open('waf.bat', 'wb')
		f.write('@python -x waf %* & exit /b\n')
		f.close()

	if sys.platform != 'win32':
		os.chmod('waf', 0755)
	os.unlink('%s.tar.%s' % (mw, zipType))

def install_waf():
	print "installing waf on the system"

	import shutil, re
	if sys.platform == 'win32':
		print "installing waf on windows is not possible yet"
		sys.exit(0)

	destdir = None
	if "DESTDIR" in os.environ:
		destdir = os.environ["DESTDIR"]
	elif Params.g_options.destdir:
		destdir = Params.g_options.destdir

	if destdir:
		prefix = "%s%s"%(destdir,Params.g_options.prefix)
	else:
		prefix = Params.g_options.prefix

	binpath     = os.path.join(prefix, 'bin%swaf' % os.sep)
	wafadmindir = os.path.join(prefix, 'lib%swaf-%s-%s%swafadmin%s' % (os.sep, VERSION, REVISION, os.sep, os.sep))
	toolsdir    = os.path.join(wafadmindir, 'Tools' + os.sep)

	try: os.makedirs(os.path.join(prefix, 'bin'))
	except: pass

	try: os.makedirs(toolsdir)
	except: pass

	try:
		pyFileExp = re.compile(".*\.py$")
		wafadminFiles = os.listdir('wafadmin')
		wafadminFiles = filter (lambda s: pyFileExp.match(s), wafadminFiles)
		for pyFile in wafadminFiles:
			if pyFile == "Test.py": continue
			shutil.copy2(os.path.join('wafadmin', pyFile), os.path.join(wafadmindir, pyFile))
		tooldir = 'wafadmin'+os.sep+'Tools'
		wafadminFiles = os.listdir(tooldir)
		wafadminFiles = filter (lambda s: pyFileExp.match(s), wafadminFiles)
		for pyFile in wafadminFiles:
			if pyFile == "Test.py": continue
			shutil.copy2(os.path.join(tooldir, pyFile), os.path.join(toolsdir, pyFile))

		shutil.copy2('waf', os.path.join(binpath))
	except:
		print "->>> installation failed: cannot write to %s <<<-" % prefix
		sys.exit(1)
	print "waf is now installed in %s [%s, %s]" % (prefix, wafadmindir, binpath)

	Params.warning("make sure to set PATH to %s/bin:$PATH" % prefix)

def uninstall_waf():
	print "uninstalling waf from the system"
	prefix  = Params.g_options.prefix
	binpath = os.path.join(prefix, 'bin%swaf' % os.sep)

	libpath = os.path.join(prefix, 'lib')
	lst = os.listdir(libpath)
	for f in lst:
		if f.startswith('waf-'):
			try: shutil.rmtree(os.path.join(libpath, f))
			except: pass

	try: os.unlink(binpath)
	except: pass

	try:
		os.stat(wafdir)
		print 'WARNING: the waf directory %s could not be removed' % wafdir
	except:
		pass

# the init function is called right after the command-line arguments are parsed
# it is run before configure(), build() and shutdown()
# in this case it calls sys.exit(0) to terminate the program
def init():
	if Params.g_options.setver: # maintainer only (ita)
		ver = Params.g_options.setver
		os.popen("""perl -pi -e 's/^VERSION=(.*)?$/VERSION="%s"/' wscript""" % ver).close()
		os.popen("""perl -pi -e 's/^VERSION=(.*)?$/VERSION="%s"/' waf-light""" % ver).close()
		os.popen("""perl -pi -e 's/^g_version(.*)?$/g_version="%s"/' wafadmin/Params.py""" % ver).close()
		sys.exit(0)
	elif Params.g_commands['install']:
		create_waf()
		install_waf()
		sys.exit(0)
	elif Params.g_commands['uninstall']:
		uninstall_waf()
		sys.exit(0)
	elif Params.g_options.waf:
		create_waf()
		sys.exit(0)
	elif Params.g_commands['check']:
		import Test
		Test.run_tests()
		sys.exit(0)
	else:
		print "run 'waf --help' to know more about allowed commands !"
		sys.exit(0)

def dist():
	import Scripting
	Scripting.g_dist_exts += ['Weak.py'] # shows how to exclude a file from dist
	Scripting.Dist(APPNAME, VERSION)

