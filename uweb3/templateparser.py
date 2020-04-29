#!/usr/bin/python2.5
"""uWeb TemplateParser

Classes:
  Parser: Parses a template by replacing tags with their values.

Error classes:
  Error: Base class for all errors generated by this module
  TemplateKeyError: A tagname
  TemplateReadError: Template file could not be read or found.
"""
__author__ = ('Elmer de Looff <elmer@underdark.nl>',
              'Jan Klopper <jan@underdark.nl>')
__version__ = '1.6'

# Standard modules
import os
import re
import urllib.parse as urlparse
from .ext_lib.underdark.libs.safestring import *
import hashlib
import itertools

class Error(Exception):
  """Superclass used for inheritance and external exception handling."""


class TemplateKeyError(Error):
  """The replaced tag has no index, key or attribute of the given value."""


class TemplateNameError(Error):
  """The referenced tag or function does not exist."""


class TemplateValueError(Error, ValueError):
  """There is a mismatch on the number of values, or the value is invalid."""


class TemplateTypeError(Error, TypeError):
  """Inappropriate argument type, or wrong number of arguments."""


class TemplateSyntaxError(Error):
  """The template contains illegal syntax."""


class TemplateReadError(Error, IOError):
  """Template file could not be read or found."""


class LazyTagValueRetrieval(object):
  """Provides a means for lazy tag value retrieval.

  This is necessary for instance for TemplateConditional.Expression, where
  lazy retrieval of tag values means that shortcircuit conditional expressions
  become possible.
  """
  def __init__(self, values):
    self._values = values
    self._tags = {}

  # ############################################################################
  # Methods for delayed tag value retrieval
  #
  def __getitem__(self, key):
    return self._tags[key].GetValue(self._values)

  def __setitem__(self, key, value):
    self._tags[key] = value

  # ############################################################################
  # Methods for minimum dictionary likeness
  #
  def __iter__(self):
    return iter(self._tags)

  def iteritems(self):
    """Returns an iterator for the items of the LazyTagValueRetrieval dict."""
    return ((key, self[key]) for key in self)

  def iterkeys(self):
    """Returns an iterator for the keys of the LazyTagValueRetrieval dict."""
    return iter(self)

  def itervalues(self):
    """Returns an iterator for the values of the LazyTagValueRetrieval dict."""
    return (self[key] for key in self)

  def items(self):
    """Returns a list with the items of the LazyTagValueRetrieval dict."""
    return list(self.iteritems())

  def keys(self):
    """Returns a list with the keys of the LazyTagValueRetrieval dict."""
    return list(self)

  def values(self):
    """Returns a list with the values of the LazyTagValueRetrieval dict."""
    return list(self.itervalues())


class Parser(dict):
  """A template parser that loads and caches templates and parses them by name.

  After initializing the parser with a search path for templates, new templates
  can be explicitly added by using the `AddTemplate` method, or by using either
  key-based access or using the `Parse` method. These templates are loaded from
  file, though inserted into the Parser cache are Template objects. These are
  constructed into their separate components for faster parsing.

  The `Parse` method takes a template name and any number of keyword arguments.
  The template name is used to fetch the desired Template object from the
  Parser cache (or to load it automatically). This Template object is then
  parsed using the provided keyword arguments.

  Alternatively, there is the `ParseString` method, which works in much the same
  way as the `Parse` method, but the first argument here is a raw template
  string instead.

  Beyond parsing, the parser grants easy access to the TAG_FUNCTIONS dictionary,
  providing the `RegisterFunction` method to add or replace functions in this
  module constant.
  """
  def __init__(self, path='.', templates=(), noparse=False):
    """Initializes a Parser instance.

    This sets up the template directory and preloads any templates given.

    Arguments:
      % path: str ~~ '.'
        Search path for loading templates using AddTemplate().
      % templates: iter of str ~~ None
        Names of templates to preload.
      % noparse: Bool ~~ False
        Skip parsing the templates to output, instead return their
        structure and replaced values
    """
    super(Parser, self).__init__()
    self.template_dir = path
    self.noparse = noparse
    for template in templates:
      self.AddTemplate(template)

  def __getitem__(self, template):
    """Retrieves a stored template by name.

    If the template is not already present, it will be loaded from disk.
    The template name will be searched on the defined `template_dir`, if it's
    not found a `TemplateReadError` is raised.

    Arguments:
      @ template: str
        Template name, or the relative path to find it on.

    Raises:
      TemplateReadError: Template name doesn't exist and cannot be loaded.

    Returns:
      Template: A template object, created from a previously loaded file.
    """
    if template not in self:
      self.AddTemplate(template)
    return super(Parser, self).__getitem__(template)

  def AddTemplate(self, location, name=None):
    """Reads the given `template` filename and adds it to the cache.

    The `template` argument should be a path/filename. This will be resolved
    against the configured template directory. The file is parsed and placed in
    the cache using the `template` filename, or the provided `name`.

    Arguments:
      @ location: str
        Location of the template file that should be loaded
      % name: str ~~ None
        Optional name to store the the file as in the cache, instead of the
        template name itself.

    Raises:
      TemplateReadError: When the template file cannot be read
    """
    try:
      template_path = os.path.join(self.template_dir, location)
      self[name or location] = FileTemplate(template_path, parser=self)
    except IOError:
      raise TemplateReadError('Could not load template %r' % template_path)

  def Parse(self, template, **replacements):
    """Returns the referenced template with its tags replaced by **replacements.

    This method automatically loads the referenced template if it doesn't exist.
    The template is loaded from the `template_dir` defined on the instance.

    Arguments:
      @ template: str
        Template name, or the relative path to find it on.
      @ **replacements: dict
        Dictionary of replacement objects. Tags are looked up in here.

    Returns:
      str: The template with relevant tags replaced by the replacement dict.
    """
    return self[template].Parse(**replacements)

  def ParseString(self, template, **replacements):
    """Returns the given `template` with its tags replaced by **replacements.

    Arguments:
      @ template: str
        The literal template string, where tags are replaced. This is not stored
        in the internal template dictionary, nor is it requested therein.
      @ replacements: dict
        Dictionary of replacement objects. Tags are looked up in here.


    Returns:
      str: template with replaced tags.
    """
    return Template(template, parser=self).Parse(**replacements)

  @staticmethod
  def RegisterFunction(name, function):
    """Registers a templating `function`, allowing use in templates by `name`.

    Arguments:
      @ name: str
        The name of the template function. This can be used behind a pipe ( | )
      @ function: function
        The function that should be used. Ideally this returns a string.
    """
    TAG_FUNCTIONS[name] = function

  TemplateReadError = TemplateReadError


class Template(list):
  """Contained for template parts, allowing for rich content construction."""
  FUNCTION = re.compile(r'\{\{\s*(.*?)\s*\}\}')
  # For a full tag syntax explanation, refer to the TAG regex in TemplateTag.
  TAG = re.compile("""
      (\[\w+                      # Tag start and alphanum tagname
        (?:(?::[\w-]+)+)?           # 0+ indices, alphanum with dashes
        (?:(?:\|[\w-]+              # 0+ functions, alphanum with dashes
          (?:\([^()]*?\))?            # closure parentheses and arguments
        )+)?                        # end of function block
      \])                         # end of tag""",
      re.VERBOSE)
  
  def __init__(self, raw_template, parser=None):
    """Initializes a Template from a string.

    Arguments:
      @ raw_template: str
        The string that represents the template.
      % parser: Parser ~~ None
        An optional parser instance that is necessary to enable support for
        adding files to the current template. This is used by {{ inline }}.
    """
    super(Template, self).__init__()
    self.parser = parser
    self.scopes = [self]
    self.AddString(raw_template)

  def __eq__(self, other):
    """Returns the equality to another Template.

    Two templates are equal if they are of the same type, and have the same
    content for their unparsed template; or string representation.
    """
    return isinstance(other, Template) and str(other) == str(self)

  def __mod__(self, kwds):
    """Syntactic sugar that enables percent-sign template parsing.

    The provided keywords MUST be in a dictionary.
    """
    return self.Parse(**kwds)

  def __repr__(self):
    return '%s(%s)' % (type(self).__name__, list(self))

  def __str__(self):
    return ''.join(map(str, self))

  def AddFile(self, name):
    """Extends the Template by reading template data from a file.

    The file is loaded through the Parser instance associated with the template.
    If there is none associated, this will raise a TypeError.

    Raises:
      TemplateReadError: The template file could not be read by the Parser.
      TypeError: There is no parser associated with the template.
    """
    if self.parser is None:
      raise TypeError('The template requires parser for adding template files.')
    return self._AddToOpenScope(self.parser[name])

  def AddString(self, raw_template):
    """Extends the Template by adding a raw template string.

    The given template is parsed and added to the existing template.

    Raises:
      TemplateSyntaxError: Unbalanced number of scopes in added template.
    """
    scope_depth = len(self.scopes)
    nodes = self.FUNCTION.split(raw_template)
    for index, node in enumerate(nodes):
      if index % 2:
        self._ExtendFunction(node)
      else:
        self._ExtendText(node)
    if len(self.scopes) != scope_depth:
      scope_diff = len(self.scopes) - scope_depth
      if scope_diff < 0:
        raise TemplateSyntaxError('Closed %d scopes too many' % abs(scope_diff))
      raise TemplateSyntaxError('Template left %d open scopes.' % scope_diff)

  def Parse(self, returnRawTemplate=False, **kwds):
    """Returns the parsed template as SafeString.

    The template is parsed by parsing each of its members and combining that.
    """
    htmlsafe = HTMLsafestring(''.join(tag.Parse(**kwds) for tag in self))
    htmlsafe.content_hash = hashlib.md5(htmlsafe.encode()).hexdigest()
    if returnRawTemplate:
      raw = HTMLsafestring(self)
      raw.content_hash = htmlsafe.content_hash
      return raw

    if self.parser and self.parser.noparse:
      #Hash the page so that we can compare on the frontend if the html has changed
      htmlsafe.page_hash = hashlib.md5(HTMLsafestring(self).encode()).hexdigest()
      #Hashes the page and the content so we can know if we need to refresh the page on the frontend
      htmlsafe.tags = {}
      for tag in self:
        if isinstance(tag, TemplateConditional):
          for flattend_branch in list(itertools.chain(*tag.branches)):
            for branch_tag in flattend_branch:
              if isinstance(branch_tag, TemplateTag):
                htmlsafe.tags[str(branch_tag)] = branch_tag.Parse(**kwds)
        if isinstance(tag, TemplateTag):
          htmlsafe.tags[str(tag)] = tag.Parse(**kwds)
    return htmlsafe

  @classmethod
  def TagSplit(cls, template):
    """Yields the TemplateTag and TemplateText nodes from a template string."""
    for index, node in enumerate(cls.TAG.split(template)):
      if index % 2:
        yield TemplateTag.FromString(node)
      elif node:
        yield TemplateText(node)

  def _ExtendFunction(self, nodes):
    """Processes a function node and adds its results to the Template.

    For loops, a new scope level is opened by adding the TemplateLoop to the
    `scopes` instance attribute. Upon finding the end of a loop, the topmost
    scope is removed, provided it is a TemplateLoop scope. If it is not,
    TemplateSyntaxError is raised.

    Raises:
      TemplateSyntaxError: Unexpected / unknown command or otherwise bad syntax.
    """
    nodes = nodes.split()
    function = nodes.pop(0)
    try:
      getattr(self, '_TemplateConstruct%s' % function.title())(*nodes)
    except AttributeError:
      raise TemplateSyntaxError('Unknown template function {{ %s }}' % function)

  def _ExtendText(self, node):
    """Processes a text node and adds its tags and texts to the Template."""
    for node in self.TagSplit(node):
      self._AddToOpenScope(node)

  # ############################################################################
  # Template syntax constructs
  #
    
  def _TemplateConstructXsrf(self, value):
    self.AddString('<input type="hidden" value="{}" name="xsrf" />'.format(value))
    
  def _TemplateConstructInline(self, name):
    """Processing for {{ inline }} template syntax."""
    self.AddFile(name)

  def _TemplateConstructFor(self, *nodes):
    """Processing for {{ for }} template syntax."""
    self._StartScope(TemplateLoop(nodes[-1], nodes[:-2]))

  def _TemplateConstructEndfor(self):
    """Processing for {{ endfor }} template syntax."""
    self._CloseScope(TemplateLoop)

  def _TemplateConstructIf(self, *nodes):
    """Processing for {{ if }} template syntax."""
    self._StartScope(TemplateConditional(' '.join(nodes)))

  def _TemplateConstructIfpresent(self, *nodes):
    """Processing for {{ ifpresent }} template syntax."""
    self._StartScope(TemplateConditionalPresence(' '.join(nodes)))

  def _TemplateConstructIfnotpresent(self, *nodes):
    """Processing for {{ ifnotpresent }} template syntax."""
    self._StartScope(TemplateConditionalPresence(' '.join(nodes), checking_presence=True))

  def _TemplateConstructElif(self, *nodes):
    """Processing for {{ elif }} template syntax."""
    self._VerifyOpenScope(TemplateConditional)
    self.scopes[-1].Elif(' '.join(nodes))

  def _TemplateConstructElse(self):
    """Processing for {{ else }} template syntax."""
    self._VerifyOpenScope(TemplateConditional)
    self.scopes[-1].Else()

  def _TemplateConstructEndif(self):
    """Processing for {{ endif }} template syntax."""
    self._CloseScope(TemplateConditional)

  # ############################################################################
  # Methods for scope management
  #
  def _AddToOpenScope(self, item):
    """Adds a template part to the current open scope."""
    self.scopes[-1].append(item)

  def _CloseScope(self, scope_cls):
    """Closes the current open scope, if it's of the given scope type.

    If the open scope is not an instance of the given scope class,
    TemplateSyntaxError is raised.
    """
    if not isinstance(self.scopes[-1], scope_cls):
      raise TemplateSyntaxError('Tried to close %s, but open scope is %s' % (
          scope_cls.__name__, type(self.scopes[-1]).__name__))
    self.scopes.pop()

  def _StartScope(self, scope):
    """Adds the given part to the template and adds it as new current scope."""
    self._AddToOpenScope(scope)
    self.scopes.append(scope)

  def _VerifyOpenScope(self, scope_cls):
    """Verifies the given `scope_cls` is the current open scope.

    If this is not the case, TemplateSyntaxError is raised.
    """
    if not isinstance(self.scopes[-1], scope_cls):
      raise TemplateSyntaxError('Expected open scope %s, but scope is %s' % (
          scope_cls.__name__, type(self.scopes[-1]).__name__))


class FileTemplate(Template):
  """Template class that loads from file."""
  def __init__(self, template_path, parser=None):
    """Initializes a FileTemplate based on a given template path.

    Arguments:
      @ template_path: str
        A string to begin a template with. This is parsed and used to build the
        initial raw template from.
      % parser: Parser ~~ None
        An optional parser instance that is necessary to enable support for
        adding files to the current template. This is used by {{ inline }}.
    """
    self._template_path = template_path
    try:
      self._file_name = os.path.abspath(template_path)
      self._file_mtime = os.path.getmtime(self._file_name)
      raw_template = open(self._file_name).read()
      super(FileTemplate, self).__init__(raw_template, parser=parser)
    except (IOError, OSError):
      raise TemplateReadError('Cannot open: %r' % template_path)

  def Parse(self, **kwds):
    """Returns the parsed template as SafeString.

    The template is parsed by parsing each of its members and combining that.
    """
    self.ReloadIfModified()
    result = super(FileTemplate, self).Parse(**kwds)
    if self.parser and self.parser.noparse:
      return {'template': self._file_name.rsplit('/')[-1],
              'replacements': result.tags,
              'content_hash':result.content_hash,
              'page_hash': result.page_hash
              }
    return result

  def ReloadIfModified(self):
    """Reloads the template file if it was modified on disk.

    If the template is not present, cannot be read, or there is another error
    accessing the file, the operation is aborted and the old template is left
    in place.

    If the new template has a syntax error or other problem during loading,
    that error *will* be raised.
    """
    try:
      mtime = os.path.getmtime(self._file_name)
      if mtime > self._file_mtime:
        template = open(self._file_name).read()
        del self[:]
        self.scopes = [self]
        self.AddString(template)
        self._file_mtime = mtime
    except (IOError, OSError):
      # File cannot be stat'd or read. No longer exists or we lack permissions.
      # We shouldn't error in this case, but carry on with the template we have.
      pass


class TemplateConditional(object):
  """A template construct to control flow based on the value of a tag."""
  def __init__(self, expr, checking_presence=True):
    self.checking_presence = checking_presence
    self.branches = []
    self.default = None
    self.NewBranch(expr)

  def __repr__(self):
    repr_branches = []
    for expr, branch in self.branches:
      clause = 'IF' if not repr_branches else 'ELIF'
      repr_branches.append('%s %r { %r }' % (clause, expr, branch))
    if self.default:
      repr_branches.append(' ELSE { %r }' % self.default)
    return '%s(%s)' % (type(self).__name__, ''.join(repr_branches))

  def __str__(self):
    repr_branches = []
    for expr, branch in self.branches:
      clause = 'if' if not repr_branches else 'elif'
      repr_branches.append('{{ %s %s }}%s' % (
          clause, ''.join(map(str, expr)), ''.join(map(str, branch))))
    if self.default:
      repr_branches.append('{{ else }}%s' % ''.join(map(str, self.default)))
    repr_branches.append('{{ endif }}')
    return '\n' + '\n'.join(repr_branches)

  def append(self, part):
    """Appends a template part to the current open conditional clause.

    Conditional clauses are not explicitly closed, a new one is simply stacked
    on top. Whenever the {{ else }} statement is found, all append actions will
    append to the else clause.
    """
    if self.default is not None:
      self.default.append(part)
    else:
      self.branches[-1][1].append(part)

  def Elif(self, expr):
    """Starts an `elif` clause.

    This raises TemplateSyntaxError if the `else` clause is already started.
    """
    if self.default is not None:
      raise TemplateSyntaxError('{{ elif }} clause may not follow {{ else }}.')
    self.NewBranch(expr)

  def Else(self):
    """Starts the `else` clause.

    This raises TemplateSyntaxError if the `else` clause is already started.
    """
    if self.default is not None:
      raise TemplateSyntaxError('Only one {{ else }} clause is allowed.')
    self.default = []

  @staticmethod
  def Expression(expr, **kwds):
    """Returns the eval()'ed result of a tag expression."""
    nodes = []
    local_vars = LazyTagValueRetrieval(kwds)
    for num, node in enumerate(expr):
      if isinstance(node, TemplateTag):
        node_name = '__tmpl_var_%d' % num
        local_vars[node_name] = node
        nodes.append(node_name)
      else:
        nodes.append(node)
    try:
      #XXX(Elmer): This uses eval, it's so much easier than lexing and parsing
      return eval(''.join(nodes), None, local_vars)
    except NameError as error:
      raise TemplateNameError(str(error).capitalize() + '. Try it as tagname?')

  def NewBranch(self, expr):
    """Begins a new branch based on the given expression."""
    self.branches.append((tuple(Template.TagSplit(expr)), []))

  def Parse(self, **kwds):
    """Returns the TemplateConditional parsed as string.

    One by one, the `if` clause and optional `elif` clauses are evaluated.
    Their strings are parsed (template tags replaced, though functions are NOT
    processed) and the resulting expression evaluated. Strings passed into the
    templateparser will be strings for evaluation (not literal code), so this
    is safe with regards to users executing code in the templateparser scope.

    Whenever a boolean True value is returned from eval, the corresponding
    branch is parsed and returned. When none of the `if` or `elif` clauses
    is True, the `else` branch is parsed and returned (where available, if no
    `else` branch exists '' is returned.
    """
    for expr, branch in self.branches:
      if type(self) == TemplateConditionalPresence:
        kwds['checking_presence'] = True
      if self.Expression(expr, **kwds):
        return ''.join(part.Parse(**kwds) for part in branch)
    if self.default:
      return ''.join(part.Parse(**kwds) for part in self.default)
    return ''

  

class TemplateConditionalPresence(TemplateConditional):
  """A template construct to safely check for the presence of tags."""

  @staticmethod
  def Expression(tags, **kwds):
    """Checks the presence of all tags named on the branch."""
    try:
      for tag in tags:
        tag.GetValue(kwds)
      if kwds.get('checking_presence'):
        return True
      return False
    except (TemplateKeyError, TemplateNameError):
      if kwds.get('checking_presence'):
        return False
      return True

  def NewBranch(self, tags):
    """Begins a new branch based on the given tags."""
    self.branches.append((map(TemplateTag.FromString, tags.split()), []))
    
class TemplateLoop(list):
  """Template loops are used to repeat a portion of template multiple times.

  Upon parsing, the loop tag is retrieved, and for each of its members, the
  items in the loop are parsed. The loop variable is made available as the given
  alias, which itself can be referenced as a tag in the loop body.
  """
  def __init__(self, tag, aliases):
    """Initializes a TemplateLoop instance.

    Arguments:
      @ tag: str
        The tag to retrieve the iterable from.
      @ aliases: *str
        The alias(es) under which the loop variable should be made available.
    """
    try:
      tag = TemplateTag.FromString(tag)
    except TemplateSyntaxError:
      raise TemplateSyntaxError('Tag %r in {{ for }} loop is not valid' % tag)

    super(TemplateLoop, self).__init__()
    self.aliases = ''.join(aliases).split(',')
    self.aliascount = len(self.aliases)
    self.tag = tag

  def __repr__(self):
    return '%s(%s)' % (type(self).__name__, list(self))

  def __str__(self):
    return '\n{{ for %s in %s }}%s\n{{ endfor }}' % (
        ', '.join(self.aliases), self.tag, ''.join(map(str, self)))

  def Parse(self, **kwds):
    """Returns the TemplateLoop parsed as string.

    Firstly, the value for the loop tag is retrieved. For each item in this
    iterable, all members of the TemplateLoop body will be parsed, with the
    item from the iterable added to the replacements dict as alias(es).
    """
    output = []
    replacements = kwds.copy()
    for item in self.tag.Iterator(**kwds):
      if self.aliascount == 1:
        replacements[self.aliases[0]] = item
      else:
        try:
          if self.aliascount != len(item):
            raise TemplateValueError('Cannot unpack %d values into %d tags' % (
                len(item), self.aliascount))
        except TypeError:
          raise TemplateValueError(
              'Cannot unpack %s into %d tags' % (type(item), self.aliascount))
        replacements.update(zip(self.aliases, item))
      output.append(''.join(tag.Parse(**replacements) for tag in self))
    return ''.join(output)


class TemplateTag(object):
  """Template tags are used for dynamic placeholders in templates.

  Their final value is determined during parsing. For more explanation on this,
  refer to the documentation for Parse().
  """
  PFX_INDEX = ':'
  PFX_FUNCT = '|'
  TAG = re.compile("""
      \[                  # Tag starts with opening bracket
        (\w+)               # Capture tagname (1+ alphanum length)
        ((?::[\w-]+)+)?     # Capture 0+ indices (1+ alphanum+dashes length)
        ((?:\|[\w-]+        # Capture 0+ functions (1+ alphanum+dashes length)
          (?:\([^()]*?\))?    # Functions may be closures with arguments.
        )+)?                # // end of optional functions
      \]                  # // end of tag""",
      re.VERBOSE)
  FUNC_FINDER = re.compile('\|([\w-]+(?:\([^()]*?\))?)')
  FUNC_CLOSURE = re.compile('(\w+)\((.*)\)')

  def __init__(self, name, indices=(), functions=()):
    """Initializes a TemplateTag instant.

    Arguments:
      @ name: str
        The name of the tag, to retrieve it from the replacements dictionary.
      % indices: iterable ~~ None
        Indices that should be applied to arrive at the proper tag value.
      % functions: iterable ~~ None
        Names of template functions that should be applied to the value.
    """
    self.name = name
    self.indices = indices
    self.functions = functions
  

  def __repr__(self):
    return '%s(%r)' % (type(self).__name__, str(self))

  def __str__(self):
    return '[%s%s%s]' % (
        self.name,
        ''.join(self.PFX_INDEX + index for index in self.indices),
        ''.join(self.PFX_FUNCT + func for func in self.functions))

  @classmethod
  def _GetFunctions(cls, raw_functions):
    if raw_functions:
      return tuple(cls.FUNC_FINDER.findall(raw_functions))
    return ()

  @classmethod
  def _GetIndices(cls, raw_indices):
    if raw_indices:
      return raw_indices.lstrip(cls.PFX_INDEX).split(cls.PFX_INDEX)
    return ()

  @classmethod
  def FromString(cls, tag):
    """Returns a TemplateTag object which is parsed from the given string.

    A tag's formatting restrictions are as follows:
      * The whole tag is delimited by square brackets: []
      * Indices are separated by colons, :, multiple are allowed
      * Functions are prefixed by pipes, |, multiple are allowed
      * In addition to the characters stated above, tags may contain only
        alphanumeric values, underscores and dashes. Spaces are _not_ allowed.
    """
    try:
      name, indices, functions = cls.TAG.match(tag).groups()
      return cls(name, cls._GetIndices(indices), cls._GetFunctions(functions))
    except AttributeError:
      raise TemplateSyntaxError('Invalid Tag syntax: %r' % tag)

  def GetValue(self, replacements):
    """Returns the value for the tag, after reducing indices.

    For a tag with indices, these are looked up one after the other, each index
    being that of the next step. [tag:0:0] for with a keyword tag=[['foo']]
    would given 'foo' as the value for the tag.
    """
    try:
      value = replacements[self.name]
      for index in self.indices:
        value = self._GetIndex(value, index)
      return value
    except KeyError:
      raise TemplateNameError('No replacement with name %r' % self.name)

  @classmethod
  def ApplyFunction(cls, func, value):
    closure = cls.FUNC_CLOSURE.match(func)
    try:
      if not closure:
        return TAG_FUNCTIONS[func](value)
      func, args = closure.groups()
      #XXX(Elmer): This uses eval, it's so much easier than lexing and parsing
      args = eval(args + ',') if args.strip() else ()
      return TAG_FUNCTIONS[func](*args)(value)
    except SyntaxError:
      raise TemplateSyntaxError('Invalid argument syntax: %r' % args)
    except TypeError as err_obj:
      raise TemplateTypeError(
          ('Templatefunction raised an TypeError %s(%s) ' % (func, value), err_obj))
    except KeyError as err_obj:
      raise TemplateNameError(
          'Unknown template tag function %r' % err_obj.args[0])

  def Parse(self, **kwds):
    """Returns the parsed string of the tag, using given replacements.

    Firstly, the tag's name is retrieved from the given replacements dictionary.

    After that, for a tag with indices, these are looked up one after the other,
    each index being that of the next step. `[tag:0:0]` with a replacements
    dictionary {tag=[['foo']]} will reduce to 'foo' as the value for the tag.

    After reducing indexes, functions are applied. As before, functions are
    applied one after the other. The second function works on the result of the
    first. If no functions are defined for a tag, the default tag function
    will be applied. SafeString objects are exempt from this default function;
    They will only be acted upon by functions as specified in the tag.

    All tag functions are derived from the module constant TAG_FUNCTIONS, and
    are looked up when requested. This means that if a function is changed after
    the template has been created, the new function will be used instead.
    """
    try:
      value = self.GetValue(kwds)
    except (TemplateKeyError, TemplateNameError):
      # On any failure to get the given index, return the unmodified tag.
      return str(self)
    # Process functions, or apply default if value is not HTMLsafestring
    if self.functions:
      for func in self.functions:
        value = self.ApplyFunction(func, value)
    else:
      if not isinstance(value, Basesafestring):
        value = TAG_FUNCTIONS['default'](value)
    return str(value)

  def Iterator(self, **kwds):
    """Parses the tag for iteration purposes.

    Functions are processed, but no defaults or other conversion is done. Tags
    that cannot be resolved result in empty iterators.
    """
    try:
      value = self.GetValue(kwds)
    except TemplateKeyError:
      # On any failure to get the given index, return an empty iterator
      return ()
    for func in self.functions:
      value = TAG_FUNCTIONS[func](value)
    return iter(value)


  @staticmethod
  def _GetIndex(haystack, needle):
    """Returns the `needle` from the `haystack` by index, key or attribute name.

    Arguments:
      @ haystack: obj
        The searched object; iterable, mapping or any kind of object.
      @ needle: str
        The index, key or attribute name to find on the haystack.

    Raises:
      TemplateKeyError: One or more of the given needles don't exist.

    Returns:
      obj: the object existing on `needle` in `haystack`.
      """
    try:
      if needle.isdigit():
        try:
          # `needle` is a number; likely an index or a numeric dict-key.
          return haystack[int(needle)]
        except KeyError:
          # `haystack` should be a dict; numeric attributes are invalid syntax.
          return haystack[needle]
      try:
        # `needle` is a string; either a dict-key, or an attribute name.
        return haystack[needle]
      except (KeyError, TypeError):
        # KeyError, `haystack` has no key `needle` but may have matching attr.
        # TypeError: `haystack` is no mapping but may have a matching attr.
        return getattr(haystack, needle)
    except (AttributeError, LookupError):
      raise TemplateKeyError('Item has no index, key or attribute %r.' % needle)


class TemplateText(str):
  """A raw piece of template text, upon which no replacements will be done."""
  def __new__(cls, string):
    return super(TemplateText, cls).__new__(cls, string)

  def __repr__(self):
    """Returns the object representation of the TemplateText."""
    return '%s(%r)' % (type(self).__name__, str(self))

  def Parse(self, **_kwds):
    """Returns the string value of the TemplateText."""
    return str(self)


TAG_FUNCTIONS = {
    'default': lambda d: HTMLsafestring('') + d, #HtmlEscape,
    'html': lambda d: HTMLsafestring('') + d, #HtmlEscape,
    'raw': lambda x: x,
    'url': lambda d: URLqueryargumentsafestring(d, unsafe=True),
    'items': lambda d: list(d.items()),
    'values': lambda d: list(d.values()),
    'sorted': sorted,
    'len': len}
