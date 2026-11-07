// Documentation types: validation and checking occur independently on server.
export type Ref=string;
export type Symbol={op:"EPS"}|{op:"TERM";value:string}|{op:"NT_REF";name:string};
export interface Grammar {schema:"formal-grammar-ir/1";terminals:string[];nonterminals:string[];start:string;productions:{id:string;lhs:string;rhs:Symbol[]}[]}
export interface DFA {schema:"formal-dfa-ir/1";states:number[];alphabet:string[];start:number;accepting:number[];delta:{from:number;token:string;to:number}[]}
export type Link={byte_utf8:[number,number];literal:string};
export interface TextSource {text_utf8:string;sha256:Ref;spans:Link[];context_refs:Ref[];rights:string}
export type Formula={pred:string;args:{var:string}[]}|{eq:[{var:string},{var:string}]}|{not:Formula}|{and:Formula[]}|{or:Formula[]}|{quant:"forall"|"exists";var:string;sort:string;body:Formula};
export interface Candidate {schema:"formal-candidate/1";candidate_id:Ref;source_ref:Ref;source_sha256:Ref;signature:{sorts:string[];predicates:Record<string,string[]>};formula_ast:Formula;assumptions:Formula[];token_role_links:Link[];construction_trace:object[];candidate_provider:{kind:"human"|"imported"|"white_star"|"external_llm";provenance:object};type_status:"TYPED"|"TYPE_REJECTED";proof_status:"PROPOSED";alternative_parse_refs:Ref[];derivation_hash:Ref;limitation_tags:string[];execution_permission:false}
export interface Run {schema:"formal-run/1";run_ref:Ref;status:"RUNNING"|"COMPLETED"|"FAILED";result_status?:string;result_ref?:Ref;stored_object_ref?:Ref;proof_ref?:Ref;kernel_binding:Ref;execution_permission:false}
export type NodeRef=[string,number,number];
export interface Leaf {terminal:string;index:number;source_span:[number,number]}
export interface Tree {node:NodeRef;production_id:string;children:(Leaf|Tree)[]}
export interface PackedRow {node:NodeRef;families:{production_id:string;children:(Leaf|{node:NodeRef})[]}[]}
export interface ProofBinding {schema:"formal-membership-proof/1";grammar_sha256:Ref;record_ref:Ref;source_sha256:Ref;tokens:string[];token_spans:[number,number][];bounds_sha256:Ref}
export type CFGProof=ProofBinding & {start_symbol:string} & (
 {status:"ACCEPT_WITH_WITNESS";decision:true;forest:PackedRow[];trees:Tree[];forest_complete:true;expanded_trees_complete:boolean} |
 {status:"REJECT_COMPLETE";decision:false;forest:PackedRow[];trees:[];forest_complete:true} |
 {status:"UNKNOWN_BOUND"|"UNKNOWN_CYCLE";decision:null;reason:string}
);
export type DFAProof=ProofBinding & {start_state:number} & (
 {status:"ACCEPT_WITH_WITNESS"|"REJECT_COMPLETE";decision:boolean;trace:{from:number;token:string;index:number;source_span:[number,number];target:number}[];final_state:number} |
 {status:"UNKNOWN_BOUND";decision:null;reason:string}
);
