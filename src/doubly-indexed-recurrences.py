
from utils import * 

from sympy import *
from sympy.abc import x, n, z, t, k
from sympy.core.cache import *
from sympy.core.function import UndefinedFunction
from sympy.printing.latex import latex

from functools import reduce

class AbstractGenericElement(object): 

    def accept(self, visitor): pass


class IndexedBaseGenericElement(AbstractGenericElement): 

    def __init__(self, indexed_base):
        self.indexed_base = indexed_base

    def accept(self, visitor): return visitor.forIndexedBaseGenericElement(self)

    def __getitem__(self, indexes): return self.indexed_base[indexes] 
        

class UndefinedFunctionGenericElement(AbstractGenericElement):

    def __init__(self, undefined_function):
        self.undefined_function = undefined_function

    def accept(self, visitor): return visitor.forUndefinedFunctionGenericElement(self)

    def __call__(self, *args): return self.undefined_function(*args)


class IndexingGenericElementVisitor:
    
    def __init__(self, ge): 
        self.ge = ge

    def __call__(self, *indexes):
        self.indexes = indexes
        return self.ge.accept(self)

    def forIndexedBaseGenericElement(self, ibge): return ibge[self.indexes]

    def forUndefinedFunctionGenericElement(self, ufge): return ufge(*self.indexes) 


def make_generic_element(generic_term):

    if isinstance(generic_term, IndexedBase): 
        return IndexedBaseGenericElement(generic_term)
    elif isinstance(generic_term, UndefinedFunction): 
        return UndefinedFunctionGenericElement(generic_term)
    
    raise Exception("Only `IndexedBase` or `UndefinedFunction` symbols" +
                    " are accepted to build abstract A-sequences.")

def symbolic_matrix(dims, gen_coeff_symbol, inits={}, 
                    lower=True, return_full_matrix_spec=True, diagonal_col_offset=None):

    if diagonal_col_offset is None: diagonal_col_offset = 1

    rows, cols = dims
    dims = rows, 1 + (cols-1) * diagonal_col_offset

    ge = make_generic_element(gen_coeff_symbol)
    indexer = IndexingGenericElementVisitor(ge)

    m = Matrix(*dims, lambda n,k: 0 if lower and n*diagonal_col_offset < k else indexer(n,k))
    for sym_coeff, v in inits.items(): m = Subs(m.subs(sym_coeff, v), sym_coeff, v)
    return (m, gen_coeff_symbol) if return_full_matrix_spec else m

def make_lower_triangular(m_spec, column_offset=1):
    m, generic_sym = m_spec
    m = m.copy()
    for r in range(m.rows):
        for c in range(r + column_offset, m.cols):
            m[r,c] = 0
    return m, generic_sym
            
class AbstractSequence:

    def __init__(self, rec):
        self.rec = rec
        self.other_seq = None

    def instantiate(self, r, c): pass

    def accept(self, visitor): pass

class Zsequence(AbstractSequence):
    
    def __getitem__(self, col): return self.rec if col is 0 else self.other_seq[col]

    def instantiate(self, row, col):
        
        row_sym, r = row
        col_sym, c = col
        indexed_sym, row_sym_index, col_sym_index = self.rec.lhs.args

        assert c == 0 and col_sym_index == 0, "c:{0}, col:{1}".format(c, col_sym_index)

        row_eq = Eq(row_sym_index,r)
        row_sol = solve(row_eq, row_sym)[0]
        return self.rec.subs(row_sym, row_sol)

    def accept(self, visitor): return visitor.forZsequence(self)

class Asequence(AbstractSequence): 

    def __getitem__(self, col): return self.rec if col > 0 else self.other_seq[col]

    def instantiate(self, row, col):
        
        row_sym, r = row
        col_sym, c = col
        indexed_sym, row_sym_index, col_sym_index = self.rec.lhs.args

        row_eq, col_eq = Eq(row_sym_index,r), Eq(col_sym_index,c)
        row_sol, col_sol = (solve(row_eq, row_sym)[0], solve(col_eq, col_sym)[0])
        return self.rec.subs({row_sym: row_sol, col_sym:col_sol}, simultaneous=True)

    def accept(self, visitor): return visitor.forAsequence(self)

class ExplodeRecTermsFromGF:

    def __call__(self, seq, gf_spec, indexed_sym, row_sym, col_sym, left_offset):

        self.gf_spec, self.indexed_sym, self.row_sym, self.col_sym, self.left_offset = \
            gf_spec, indexed_sym, row_sym, col_sym, left_offset

        return seq.accept(self)

    def forAsequence(self, seq):

        gf, gf_var, n = self.gf_spec
        gf_series = gf.series(gf_var, n=n)

        summands = [gf_series.coeff(gf_var, n=i) * self.indexed_sym[self.row_sym, self.col_sym + (i-self.left_offset)] 
                        for i in range(n)]

        rhs = Add(*summands, evaluate=False).doit(deep=False)
            
        return Eq(self.indexed_sym[self.row_sym+1, self.col_sym+1], rhs)

    def forZsequence(self, seq):

        gf, gf_var, n = self.gf_spec
        gf_series = gf.series(gf_var, n=n)

        summands = [gf_series.coeff(gf_var, n=i) * self.indexed_sym[self.row_sym, i] for i in range(n)]

        rhs = Add(*summands, evaluate=False).doit(deep=False)
            
        return Eq(self.indexed_sym[self.row_sym+1, 0], rhs)


class MaxColumnSubscriptVisitor:

    def __call__(self, matrix_spec, seq, row_sym, col_sym):
        self.matrix_spec, self.row_sym, self.col_sym = matrix_spec, row_sym, col_sym
        return seq.accept(self)

    def forAsequence(self, seq):
        
        matrix = self.matrix_spec[0]
        # the following substitutions for row and col symbols is greater than
        # the necessary: in reality for recurrences where lhs subscripts are {n+1, k+1}
        # as usual, then we should substitute matrix.rows-2 and matrix.cols-2, respectively.
        instantiated_rec = seq.rec.subs({self.row_sym:matrix.rows, self.col_sym:matrix.cols}, 
                                        simultaneous=True)  
        
        max_col_subscript = self.col_subscript(instantiated_rec.lhs)
        for rhs_term in explode_term_respect_to(instantiated_rec.rhs, op_class=Add):
            current_col_subscript = self.col_subscript(rhs_term)
            if current_col_subscript is None: continue
            max_col_subscript = max(max_col_subscript, current_col_subscript)
        
        return max_col_subscript

    def col_subscript(self, term):

        coeff_wild, row_wild, col_wild = Wild('coeff'), Wild('row'), Wild('col')
        indexed_sym = self.matrix_spec[1]

        matched = term.match(coeff_wild * indexed_sym[row_wild, col_wild])
        return matched[col_wild] if matched and coeff_wild in matched else None

    def forZsequence(self, seq): return self.forAsequence(seq)

class FreeVarsLocation:

    def accept(self, visitor): pass

class OnColumnZeroFreeVarsLocation(FreeVarsLocation):

    def accept(self, visitor): return visitor.forColumnZeroFreeVarsLocation(self)

class OnMainDiagonalFreeVarsLocation(FreeVarsLocation):

    def accept(self, visitor): return visitor.forMainDiagonalFreeVarsLocation(self)

class OnLastButOneUnfoldingRowFreeVarsLocation(FreeVarsLocation):

    def accept(self, visitor): return visitor.forLastButOneUnfoldingRowFreeVarsLocation(self)


class LookupFreeVariablesVisitor:

    def __call__(self, matrix_spec, unfolding_rows, location): 
        self.matrix, self.indexed_sym, self.unfolding_rows = \
            matrix_spec[0], matrix_spec[1], unfolding_rows
        return location.accept(self)

    def forColumnZeroFreeVarsLocation(self, location):
        return set(self.matrix[r,0] for r in range(self.unfolding_rows))

    def forMainDiagonalFreeVarsLocation(self, location):
        return set(self.matrix[r,r] for r in range(self.unfolding_rows))

    def forLastButOneUnfoldingRowFreeVarsLocation(self, location):
        return set(self.matrix[self.unfolding_rows-1,c] for c in range(self.unfolding_rows))


class StartingColIndexForUnfoldVisitor:

    def __call__(self, location): return location.accept(self)

    def forColumnZeroFreeVarsLocation(self, location): return 1

    def forMainDiagonalFreeVarsLocation(self, location): return 0

    def forLastButOneUnfoldingRowFreeVarsLocation(self, location): pass


class AdjustEndColumnIndexVisitor:

    def __call__(self, location, cols): 
        self.cols = cols
        return location.accept(self)

    def forColumnZeroFreeVarsLocation(self, location): return self.cols + 1

    def forMainDiagonalFreeVarsLocation(self, location): return self.cols

    def forLastButOneUnfoldingRowFreeVarsLocation(self, location): pass


class NullAdjustEndColumnIndexVisitor:

    def __call__(self, location, cols): return cols + 1

    def forColumnZeroFreeVarsLocation(self, location): pass

    def forMainDiagonalFreeVarsLocation(self, location): pass

    def forLastButOneUnfoldingRowFreeVarsLocation(self, location): pass


class EntailDependenciesVisitor():

    def __call__(self, matrix_spec, unfolding_rows, location): 
        self.matrix_spec, self.unfolding_rows = matrix_spec, unfolding_rows
        return location.accept(self)

    def forColumnZeroFreeVarsLocation(self, location):

        matrix, indexed_sym = self.matrix_spec
        return {indexed_sym[r,0]:matrix[r,0] for r in range(1, self.unfolding_rows)}

    def forMainDiagonalFreeVarsLocation(self, location):

        matrix, indexed_sym = self.matrix_spec
        return {indexed_sym[r,r]:matrix[r,r] for r in range(1, self.unfolding_rows)}

    def forLastButOneUnfoldingRowFreeVarsLocation(self, location):

        matrix, indexed_sym = self.matrix_spec
        return {indexed_sym[self.unfolding_rows-1,c]:matrix[self.unfolding_rows-1,c] 
                    for c in range(self.unfolding_rows)}


class UpperChunkUnfoldingStrategy:

    def __call__(self, location, *args, **kwds): 
        self.args, self.kwds = args, kwds
        return location.accept(self)

    def forColumnZeroFreeVarsLocation(self, location): 
        return self.forNotHorizontallyPlaced(location)

    def forMainDiagonalFreeVarsLocation(self, location):
        return self.forNotHorizontallyPlaced(location)

    def forNotHorizontallyPlaced(self, free_vars_location):

        start_col_index = StartingColIndexForUnfoldVisitor()

        return unfold_in_matrix(*self.args, 
            unfold_row_start_index=1, unfold_col_start_index=start_col_index(free_vars_location),
            include_substitutions=True, adjust_end_column_index = AdjustEndColumnIndexVisitor(), **self.kwds)

    def forLastButOneUnfoldingRowFreeVarsLocation(self, location):
        return invert_rec(*self.args, **self.kwds)


class AdjustFactorizationVisitor():

    def __call__(self, matrix_spec, factorization, location): 
        self.matrix_spec, self.factorization = matrix_spec, factorization
        return location.accept(self)

    def forColumnZeroFreeVarsLocation(self, location):

        return self.factorization

    def forMainDiagonalFreeVarsLocation(self, location):

        indexed_sym = self.matrix_spec[1]
        rows, cols = self.matrix_spec[0].rows, self.matrix_spec[0].cols
        diagonal_matrix = zeros(rows, cols)
        mixed_matrix = zeros(rows, cols)
        expansion = self.factorization['expansion']
        unfolding_rows = len(expansion)

        new_expansion = {}

        for i in range(unfolding_rows-1):
            free_variable = indexed_sym[i,i]
            inner_matrix = expansion[free_variable]

            diagonal_matrix[i,i] = diagonal_matrix[i,i] + free_variable

            rectangular_matrix = free_variable * inner_matrix[i+1:,:i]
            mixed_matrix[i+1:,:i] = mixed_matrix[i+1:,:i] + rectangular_matrix

            sub_matrix = zeros(rows, cols)
            sub_matrix[i+1:,i:] = sub_matrix[i+1:,i:] + inner_matrix[i+1:,i:]
            new_expansion[free_variable] = sub_matrix
        
        
        # handle stuff about the last variable manually
        i = unfolding_rows-1
        free_variable = indexed_sym[i,i]
        last_inner_matrix = expansion[free_variable]
        rectangular_matrix = free_variable * last_inner_matrix[i+1:,:i]
        mixed_matrix[i+1:,:i] = mixed_matrix[i+1:,:i] + rectangular_matrix
        last_sub_matrix = zeros(rows, cols)
        last_sub_matrix[i:,i:] = last_sub_matrix[i:,i:] + last_inner_matrix[i:,i:]
        new_expansion[free_variable] = last_sub_matrix

        new_expansion['diagonal'] = diagonal_matrix
        new_expansion['mixed'] = mixed_matrix

        return new_expansion


    def forLastButOneUnfoldingRowFreeVarsLocation(self, location):

        return self.factorization

def make_A_Z_sequences_from_recs(Arec, Zrec=None):

    Aseq = Asequence(Arec)
    Zseq = Aseq if Zrec is None else Zsequence(Zrec)
    return Aseq, Zseq

def unfold_in_matrix(m_spec, Arec, Zrec=None,
            unfold_row_start_index=1, unfolding_rows=None, diagonal_col_offset=None,
            unfold_col_start_index=None, row_sym=Symbol('n'), col_sym=Symbol('k'),
            include_substitutions=False, free_vars_location=OnColumnZeroFreeVarsLocation(),
            adjust_end_column_index=NullAdjustEndColumnIndexVisitor()):

    m, indexed_sym = m_spec
    m = m.copy()

    Aseq, Zseq = make_A_Z_sequences_from_recs(Arec, Zrec)

    if unfolding_rows is None: unfolding_rows = m.rows
    if diagonal_col_offset is None: diagonal_col_offset = 1
    if unfold_col_start_index is None: unfold_col_start_index = 0

    substitutions = {}
    variables = free_variables_in_matrix(m_spec, unfolding_rows, free_vars_location)
    
    for r in range(unfold_row_start_index, unfolding_rows):
        
        sequence = Aseq if unfold_col_start_index > 0 else Zseq
        cols = adjust_end_column_index(free_vars_location, cols=r * diagonal_col_offset)

        for c in range(unfold_col_start_index, cols):

            instantiated_rec = sequence.instantiate((row_sym, r), (col_sym, c))

            unfold_term = 0

            for summand in explode_term_respect_to(instantiated_rec.rhs, Add):
                coeff_wild = Wild('coeff', exclude=[indexed_sym])
                row_wild = Wild('n', exclude=[indexed_sym])
                col_wild = Wild('k', exclude=[indexed_sym])
                matched = summand.match(coeff_wild * indexed_sym[row_wild, col_wild])

                if  not matched or \
                    coeff_wild not in matched or \
                    row_wild not in matched or \
                    col_wild not in matched: 
                    continue

                inst_row_index, inst_col_index = matched[row_wild], matched[col_wild]
                coeff = matched[coeff_wild]

                if inst_row_index in range(m.rows) and inst_col_index in range(m.cols):
                    unfold_term = unfold_term + coeff * m[inst_row_index, inst_col_index]

            if c < m.cols: 
                unfold_term = Poly(unfold_term, variables).args[0]
                m[r,c] = unfold_term
                substitutions.update({indexed_sym[r,c] : unfold_term})

            sequence = Aseq

    m_spec = m, indexed_sym
    return (m_spec, substitutions) if include_substitutions else m_spec
            
def build_rec_from_gf(gf_spec, indexed_sym, seq_class=Asequence,
                      row_sym=Symbol('n'), col_sym=Symbol('k'), left_offset=0, evaluate=False):

    explode = ExplodeRecTermsFromGF()
    return explode(seq_class(None), gf_spec, indexed_sym, row_sym, col_sym, left_offset)
    
def apply_subs(m, substitutions):
    term = m
    for k,v in substitutions.items(): term = Subs(term.replace(k,v), k, v)
    return term

def factorize_each_term_respect_free_variables_location(
        matrix_spec, unfolding_rows, free_vars_location, substitutions):

    matrix, indexed_sym = matrix_spec
    variables = free_variables_in_matrix(matrix_spec, unfolding_rows, free_vars_location)
    subs_matrix = matrix.subs(substitutions, simultaneous=True).applyfunc(
                lambda term: Poly(term, variables).args[0])
    return subs_matrix, indexed_sym

def unfold_upper_chunk(*args, **kwds):

    free_vars_location = kwds['free_vars_location']
    unfolding_rows = kwds['unfolding_rows']

    upper_chunk_unfolding_strategy = UpperChunkUnfoldingStrategy()

    matrix_spec, substitutions = upper_chunk_unfolding_strategy(
        free_vars_location, *args, **kwds)

    return  factorize_each_term_respect_free_variables_location(
                matrix_spec, unfolding_rows, free_vars_location, substitutions)

def invert_rec( matrix_spec, Arec, Zrec=None, *args, unfolding_rows=None,
                diagonal_col_offset=1, row_sym=Symbol('n'), col_sym=Symbol('k'), **kwds):

    matrix, indexed_sym = matrix_spec
    Aseq, Zseq = make_A_Z_sequences_from_recs(Arec, Zrec)

    if unfolding_rows is None: unfolding_rows = matrix.rows

    substitutions = []

    for i in range(1, unfolding_rows):
        r = unfolding_rows-i

        eqs = []
        for c in range(r * diagonal_col_offset + 1):
            seq = Aseq if c > 0 else Zseq
            instantiated_rec = seq.instantiate((row_sym, r), (col_sym, c))
            eqs.append(instantiated_rec)
             
        sols = solve(eqs, check=True)
        
        assert len(sols) > 0, "r:{} provides no solutions".format(r)

        sol = sols[0]
        previous_r = r-1
        substitutions.append({term:sol[term] 
            for c in range(previous_r * diagonal_col_offset + 1)
            for term in [ indexed_sym[previous_r, c] ]})

    backwards_substitutions = {}

    for substitution in substitutions:
        backwards_substitutions.update({k:v.subs(backwards_substitutions) for k,v in substitution.items()})

    find_max_subscript = MaxColumnSubscriptVisitor()
    cols = find_max_subscript(matrix_spec, Aseq, row_sym, col_sym)
    zero_subs = {indexed_sym[r,c]:0 for r in range(0, matrix.rows) for c in range(r+1, cols+1)}
    backwards_substitutions = {k:v.subs(zero_subs) for k,v in backwards_substitutions.items()}

    return matrix_spec, backwards_substitutions

def build_rec_from_A_matrix(A_matrix): pass

def build_rec_from_A_sequence(A_sequence_spec, symbolic_row_index = Symbol('n')+1):
    A_sequence_gf, indeterminate, order = A_sequence_spec
    return build_rec_from_A_matrix({(symbolic_row_index-1) : (A_sequence, indeterminate)}, order)

def extract_inner_matrices(m_spec, unfolding_rows, diagonal_col_offset=None, free_vars_location=None):

    matrix, indexed_sym = m_spec
    
    if diagonal_col_offset is None: diagonal_col_offset = 1

    matrices = {}

    variables = free_variables_in_matrix(m_spec, unfolding_rows, free_vars_location)

    for current_symbolic_element in variables:

        nullable_variables = variables - set([current_symbolic_element])
        substitutions = {var:0 for var in nullable_variables}

        nullable_matrix = matrix.subs(substitutions, simultaneous=True)

        def worker(r, c):

            if r*diagonal_col_offset < c: return 0 

            wild_coeff = Wild("coeff")
            matched = nullable_matrix[r,c].match(wild_coeff*current_symbolic_element)

            #if not matched or wild_coeff not in matched: print("r:{} c:{} not matched: {}".format(r,c,nullable_matrix[r,c]))
            #if r==5 and c==1: print("5 1: {}".format(matched[wild_coeff]))
            #if matched[wild_coeff] == 0: print("r:{} c:{} has 0 for {}".format(r,c,current_symbolic_element))
            return matched[wild_coeff] if matched and wild_coeff in matched else 0

        matrices[current_symbolic_element] = Matrix(matrix.rows, matrix.cols, worker)

    return matrices

def check_matrix_expansion(m_spec, expansion, inits={}, perform_asserts=True):

    m, indexed_sym = m_spec

    sum_matrix = zeros(m.rows, m.cols)

    for k,v in expansion.items(): sum_matrix = sum_matrix + (k * v)

    sum_matrix = sum_matrix.subs(inits, simultaneous=True).applyfunc(
        lambda term: Poly(term, indexed_sym[0,0]).args[0])

    eq = Eq(m, sum_matrix)
    
    if eq == True: return True

    for r in range(m.rows):
        for c in range(m.cols):
            v1 = eq.lhs[r, c].expand()
            v2 = eq.rhs[r, c].expand()
            if not (v1 == v2): 
                if perform_asserts: assert False, "Row: {} Col: {} --- {} != {}".format(r, c, v1, v2)
                else: return False

    return True

def make_abstract_A_sequence(spec, inits={}):

    indexed_sym, indeterminate, order = spec

    def getter(index):
        if isinstance(indexed_sym, IndexedBase): return indexed_sym[index]
        elif isinstance(indexed_sym, UndefinedFunction): return indexed_sym(index)
        else: raise Exception("Only `IndexedBase` or `UndefinedFunction` symbols" +
                        " are accepted to build abstract A-sequences.")

    # maybe it should be better to use list comprehension like this:
    #for i in range(order): term += indexed_sym[i]*indeterminate**i
    summands = [getter(i)*indeterminate**i for i in range(order)]
    term = Add(*summands, evaluate=False).doit(deep=False)
    
    return term.subs(inits)

def entail_dependencies(unfolded_matrix_spec, unfolding_rows, free_vars_location):
    visitor = EntailDependenciesVisitor()
    return visitor(unfolded_matrix_spec, unfolding_rows, free_vars_location)

def factorize_matrix_as_matrices_sum(
        matrix_spec, length=None, perform_check=False, *args, **kwds):
    
    matrix = matrix_spec[0]

    if length is None: length = matrix.rows

    if 'free_vars_location' not in kwds or kwds['free_vars_location'] is None: 
        kwds.update({'free_vars_location':OnColumnZeroFreeVarsLocation()})

    assert length <= matrix.rows, "It was required an expansion using {} matrices when" + \
        " the provided matrix had {} rows".format(length, matrix_spec[0].rows)

    diagonal_col_offset = kwds['diagonal_col_offset'] if 'diagonal_col_offset' in kwds else None
    free_vars_location = kwds['free_vars_location']

    unfolded_matrix_spec = unfold_in_matrix(matrix_spec, *args, **kwds)
    splitted_matrix_spec = unfold_in_matrix(matrix_spec, *args, unfold_row_start_index=length, **kwds)
    clean_splitted_matrix_spec = unfold_upper_chunk(splitted_matrix_spec, *args, unfolding_rows=length, **kwds)
    matrix_expansion = extract_inner_matrices(clean_splitted_matrix_spec, length, diagonal_col_offset, free_vars_location)
    inits_dependencies = entail_dependencies(unfolded_matrix_spec, length, free_vars_location)

    if perform_check:
        should_be_true = check_matrix_expansion(unfolded_matrix_spec, matrix_expansion, inits_dependencies)
        assert should_be_true == True

    return dict(unfolded=extract_inner_matrices(unfolded_matrix_spec, 1, diagonal_col_offset, free_vars_location), 
                splitted=clean_splitted_matrix_spec[0],
                dirty_splitted=splitted_matrix_spec[0],
                expansion=matrix_expansion,
                dependencies=inits_dependencies,
                generic_symbol=unfolded_matrix_spec[1])

def instantiate_factorization(factorization, inits=None, perform_check=False):
    
    gen_sym = factorization['generic_symbol']

    if inits is None: inits = {gen_sym[0,0]:1}

    dependencies = {k:v.subs(inits) for k,v in factorization['dependencies'].items()}
    splitted = factorization['splitted'].subs(dependencies).subs(inits).applyfunc(lambda term: expand(term))
    inst_factorization = dict(  unfolded={k.subs(inits):v for k,v in factorization['unfolded'].items()},
                                splitted=splitted,
                                expansion=[(k.subs(dependencies), v) for k,v in factorization['expansion'].items()],
                                dependencies=dependencies,
                                generic_symbol=factorization['generic_symbol'])

    if perform_check:
        for k,v in inst_factorization['unfolded'].items():
            checking_matrix = k*v
            for r in range(v.rows):
                for c in range(v.cols):
                    v1 = checking_matrix[r,c].expand()
                    v2 = inst_factorization['splitted'][r, c]
                    assert v1 == v2, "Row: {} Col: {} --- {} != {}".format(r, c, v1, v2)

    return inst_factorization

def apply_factor_inside_matrix(matrix_spec, inits=None):
    
    gen_sym = matrix_spec[1]

    if inits is None: inits = {gen_sym[0,0]:1}

    return matrix_spec[0].subs(inits).applyfunc(lambda term: factor(term)), gen_sym

def adjust_expansion(matrix_spec, factorization, free_vars_location):
    adjust = AdjustFactorizationVisitor()
    return adjust(matrix_spec, factorization, free_vars_location)

def free_variables_in_matrix(matrix_spec, unfolding_rows, free_vars_location):
    
    free_vars_respect = LookupFreeVariablesVisitor()
    return free_vars_respect(matrix_spec, unfolding_rows, free_vars_location)

def clean_up_zeros(matrix_spec, label="", colors={}, 
                    environment="equation", cancel_zeros=True, diagonal_col_offset=None):

    matrix, indexed_sym = matrix_spec
    if diagonal_col_offset is None: diagonal_col_offset = 1

    tex_code = r"\begin{" + environment + r"}" + "\n" if environment else ""
    tex_code += r"\left[\begin{array}{" + ('c' * matrix.cols) + r'}' + "\n"

    for r in range(matrix.rows):
        for c in range(matrix.cols):
            
            space = "" if c == 0 else " "

            if r*diagonal_col_offset < c: coeff_str = ""
            elif cancel_zeros: coeff_str = latex(matrix[r,c]) if matrix[r,c] != 0 else ""
            else: coeff_str = latex(matrix[r,c])

            if (r,c) in colors: coeff_str = r'\textcolor{' + colors[(r,c)] + r'}{' + coeff_str + "}"
            tex_code += "{}{} {}".format(space, coeff_str, r'\\' if c == matrix.cols-1 else r'&') 

        tex_code += "" if r == matrix.rows - 1 else "\n"

    label = "\n{}".format(r'\label{eq:' + label + r'}' + "\n" if label else "")
    tex_code += "\n" + r'\end{array}\right]' 
    tex_code += label + r'\end{' + environment + '}' if environment else ""

    return tex_code

def latex_of_matrix_expansion(matrix_expansion, *args, **kwds):
    tex_code = ""
    add_code = " + "
    for k,v in matrix_expansion.items():
        tex_code += latex(k) + clean_up_zeros((v, None), *args, environment=None, **kwds)
        tex_code += add_code
    return tex_code[0:-len(add_code)]


class PascalHockeyStick:

    def set_data(self, indexed_sym, row_sym, col_sym):
        self.indexed_sym = indexed_sym
        self.row_sym = row_sym
        self.col_sym = col_sym

    def __call__(self, *args, **kwds): pass

    
class DiagonalHockeyStick(PascalHockeyStick):

    def __call__(self, i): return self.indexed_sym[self.row_sym-i, self.col_sym + 1 -i]    

class VerticalHockeyStick(PascalHockeyStick):

    def __call__(self, i): return self.indexed_sym[self.row_sym-i, self.col_sym]    

def make_pascal_hockey_stick_recurrence(indexed_sym, length, stick,
        row_sym=Symbol('n'), col_sym=Symbol('k')):
    
    stick.set_data(indexed_sym, row_sym, col_sym)

    rhs = 0
    for i in range(length): rhs = rhs + stick(i)

    return Eq(indexed_sym[row_sym+1, col_sym+1], rhs)


