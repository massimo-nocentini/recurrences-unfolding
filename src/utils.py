
import functools
from copy import copy
from contextlib import contextmanager

from sympy import *


class DestructuringError(ValueError): 
    '''
    Represent an error due to the impossibility to destructure a given term.

    At the present, we neither provide meaningful error messages nor objects
    related to the context in which this exception was raised; moreover, we
    do not distinguish the operator in the tackled combination term (Add, Mul,...).
    '''

    pass

@contextmanager
def bind_Mul_indexed(term, indexed, forbidden_terms=[]):
    '''
    Destructure `term` against pattern `coeff * f[i j ...]`, binding `coeff`, `i` and `j ...`.

    I attempt to destructure the given term respect the `Mul` operator, aiming to isolate
    term `indexed`, which should be an instance of `Indexed` class, from a coefficient `coeff`,
    which collect everything but `indexed` and, optionally, objects appearing in `forbidden_terms`.
    If such destructuring fails, then I raise `DestructuringError`.

    Examples
    ========
    
    >>> from sympy import *

    Main track, everything is good:
    >>> f, n, k, j = IndexedBase('f'), *symbols('n k j')
    >>> term = 3 * f[n,k,j]
    >>> with bind_Mul_indexed(term, f) as (coeff, subscripts):
    ...     print('{} * {}'.format(coeff, subscripts))
    3 * [n, k, j]
    
    Failure, not a vanilla product:
    >>> term = 3 * f[n] + 1
    >>> try:
    ...     with bind_Mul_indexed(term, f) as (coeff, subscripts):
    ...         print('{} * {}'.format(coeff, subscripts))
    ... except DestructuringError:
    ...     print('something else')
    something else

    Failure, `f` not indexed at all:
    >>> term = 3 * f
    >>> try:
    ...     with bind_Mul_indexed(term, f) as (coeff, subscripts):
    ...         print('{} * {}'.format(coeff, subscripts))
    ... except DestructuringError:
    ...     print('something else')
    something else
    '''

    coeff_w, ind_w = Wild('coeff', exclude=[indexed] + forbidden_terms), Wild('ind')
    matched = term.match(coeff_w * ind_w)
    # if no indexing applied then `isinstance(matched[ind_w], IndexedBase)` holds
    if (matched and ind_w in matched and coeff_w in matched 
            and isinstance(matched[ind_w], Indexed)):
        _, *subscripts = matched[ind_w].args
        yield matched[coeff_w], subscripts # do not splice subscripts, give them structured
    else:
        raise DestructuringError()


def explode_term_respect_to(term, cls, deep=False):

    exploded = [term] # at least we start with the given term since we've to build a list eventually

    if isinstance(term, cls): 
        exploded = flatten(term.expand().args, cls=cls) if deep else term.args

    return exploded

def not_evaluated_Add(*args, **kwds):
    '''
    Build an `Add` object, *not evaluated*, regardless any value for the keyword `evaluate`.
    '''
    kwds['evaluate']=False # be sure that evaluation doesn't occur
    return Add(*args, **kwds)

def symbol_of_indexed(indexed):
    '''
    Return the `Symbol` object of an indexable term, otherwise return the given argument as is.

    To be honest, any iterable with at least one element works; maybe we should do `isinstance(...)`
    checks to properly implement this function.
    '''
    try:
        indexed_sym, *rest = indexed
        return indexed_sym
    except Exception:
        return indexed

@contextmanager
def map_reduce(on, doer, reducer, initializer=None):
    '''
    Map-Reduce pipeline.
    '''
    yield functools.reduce(reducer, map(doer, on), initializer)

@contextmanager
def normalize_eq(eq, constraints):
    '''
    Normalize an equation according to its `lhs`.

    I consume an `Eq` object and, assuming in the `lhs` there's a term that defines the `rhs`,
    then I return an `Eq` object such that subscripts are in vanilla form, no offsets appear.
    '''
    normalized = eq
    for var, rel in constraints.items():
        d = Dummy()
        sol = solve(Eq(rel, d), var).pop()
        normalized = normalized.subs(var, sol).subs(d, var)
    yield normalized

@contextmanager
def instantiate_eq(eq, constraints):
    '''
    Instantiate the given `Eq` object according to the given constraints.

    Substitutions happen *not* simultaneously, therefore another implementation
    is possible using the capabilities of `subs`, namely:
        `eq.subs(constraints, simultaneous=True)`
    '''
    instantiated = eq
    for var, rel in constraints.items():
        instantiated = instantiated.subs(var, rel)
    yield instantiated

@contextmanager
def copy_recurrence_spec(recurrence_spec, **kwds):
    '''
    Build a shallow copy of the given recurrence spec, possibly updating it as desired.
    
    Updating happens in the sense of `namedtuple._replace`; however, if keyword `terms_cache` 
    isn't provided, then a shallow copy of `recurrence_spec.terms_cache` is attached to the returned spec.
    '''
    if 'terms_cache' not in kwds:
        kwds['terms_cache'] = copy(recurrence_spec.terms_cache)

    yield recurrence_spec._replace(**kwds)

@contextmanager
def fmap_on_dict(doer, on, on_key=True, on_value=True):
    '''
    Apply `doer` to the given mapping, inspired to `Functor`s in Haskell.

    It is possible to choose to apply `doer` to both (key, value) pair or only partially.
    '''
    yield {(doer(k) if on_key else k): (doer(v) if on_value else v) for k,v in on.items()}




















