from binaryninja import Function, SSAVariable, MediumLevelILCall, MediumLevelILVarSsa, MediumLevelILConstPtr, PossibleValueSet, MediumLevelILConst, MediumLevelILOperation
from dataclasses import dataclass, replace
import logging
import pprint

@dataclass
class Parameter:
    param: MediumLevelILVarSsa | MediumLevelILConstPtr | MediumLevelILConst # if the type of element of params is MLIL_VAR_SSA, ssavar is SSAVariable 
    ssavar: SSAVariable | None # if the element is constant, ssavar is None
    possible_value: PossibleValueSet

class PFEdge:
    def __init__(self, start=None, end=None, address=None, taint_args=None) -> None:
        assert start is not None and address is not None
        
        self.start: Function = start
        self.end: Function = end
        self.address: int = address
        self.instr: MediumLevelILCall
        self.parameters: dict[str, Parameter] = dict()
        '''
            {
                'arg0': Parameters
                'arg1': Parameters
                ...
            }
        '''
        self.taint_args: list[int] = taint_args
        self.return_value = None # Not implemented

        # initialize empty attributes
        self.instr = self.start.get_llil_at(self.address).mlil
        self.initialize_param()

    def __hash__(self) -> int:
        return hash(self.address)

    def __repr__(self) -> str:
        result = f'\n################  edge  ###############\n'
        result += f'Thid edge is {self.start} -> {self.end}\n'
        result += f'address: {self.address:#x}\n'
        result += f'instruction: {self.instr}\n'
        result += pprint.pformat(self.parameters) + '\n'
        result += f'taint_args: {self.taint_args}\n'
        result += f'#######################################\n'

        return result


    def initialize_param(self):
        # TODO: 전역변수일 때 확인해보기
        for idx, parameter in enumerate(self.instr.ssa_form.params):
            if type(parameter) is MediumLevelILVarSsa:
                possible_value = self.instr.ssa_form.get_ssa_var_possible_values(parameter.src)
                param = Parameter(param=parameter, ssavar=parameter.src, possible_value=possible_value)
                self.parameters[f'arg{idx}'] = param
            elif type(parameter) is MediumLevelILConst:
                possible_value = PossibleValueSet.constant(parameter.constant)
                param = Parameter(param=parameter, ssavar=None, possible_value=possible_value)
                self.parameters[f'arg{idx}'] = param
            elif type(parameter) is MediumLevelILConstPtr:
                possible_value = PossibleValueSet.constant_ptr(parameter.constant)
                param = Parameter(param=parameter, ssavar=None, possible_value=possible_value)
                self.parameters[f'arg{idx}'] = param
            else:
                logging.error(f'New type of param appear! please check arg{idx} of {self.instr} at {self.address}')
                raise NotImplemented
            logging.debug(f'arg{idx}: {param.param}, {param.ssavar}, {param.possible_value}')

    def update_possible_value(self):
        '''
        update the possible value set of arguments at end function
        '''
        for instr in self.end.mlil.ssa_form.basic_blocks[0]:
            if instr.operation == MediumLevelILOperation.MLIL_SET_VAR_SSA and \
                type(instr.src) == MediumLevelILVarSsa:
                name: str = instr.src.src.var.name

                if name.startswith('arg'):
                    key = f'arg{int(name.split("arg")[1]) - 1}' # in binary ninja name rules, it start at arg1, but arg0 in this framwork.
                    var = instr.dest.var
                    possible_value: Parameter = self.parameters[key]
                    self.end.set_user_var_value(var=var, def_addr=instr.address, value=possible_value.possible_value)

    def get_ssavars_to_taint(self) -> list[SSAVariable]:
        # taint 할 argument 중에서 ssavar 리턴하기
        # TODO: 전역변수는 어떻게 되는지 확인하기
        assert self.taint_args is not None
        ssavars = []
        for arg in self.taint_args:
            arg: int
            key = f'arg{arg}'
            param: Parameter = self.parameters[key]
            ssavars.append(param.ssavar)
        return ssavars

class PFNode:
    def __init__(self, function = None) -> None:
        assert function is not None

        self.function: Function = function
        self.prev: PFNode = None
        self.next: PFNode = None
        self.prev_at: PFEdge = None
        self.next_at: PFEdge = None
        self.tainted_vars_from_source: list[SSAVariable] = []
        self.tainted_vars_from_sink: list[SSAVariable] = []
    

    def __hash__(self) -> int:
        return hash(self.function)

    def __repr__(self) -> str:
        result = f'\n##############  node  #################\n'
        result += f'\nThis node is {self.function}\n'
        result += f'prev: {self.prev.function if self.prev is not None else None}\nnext: {self.next.function if self.next is not None else None}\n'
        if self.prev_at is not None:
            result += f'prev_at: {self.prev_at.start} -> \n'
        else:
            result += f'prev_at: None\n'
        if self.next_at is not None:
            result += f'next_at: -> {self.next_at.end}\n'
        else:
            result += f'next_at: None\n'
        
        result += f'tainted_from_source: {self.tainted_vars_from_source}\ntainted_from_sink: {self.tainted_vars_from_sink}\n'
        result += f'#######################################\n'
        return result