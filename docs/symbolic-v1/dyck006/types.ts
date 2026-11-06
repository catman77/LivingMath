/** Data-only documentation types; runtime verification is independent Python. */
export type Ref = string;
export type Instruction = {op: "ATOM_ROLE"; role: "OPEN" | "CLOSE"} | {op: "RECURSE"; branch: "b0" | "b1"};
export interface RoleProgram {
 composition: "finite_role_branching"; base: "EPS" | "NONE";
 roles: {OPEN: string; CLOSE: string}; sequence: Instruction[];
 quantifier: "FINITE_EXISTS"; combine: "BRANCH_AND"; reconstruction: "CONCAT";
}
export interface WordState {
 tokens: string[]; boundaries: [number,string,string][];
 source_spans: [Ref,number,number][][]; word_hash: Ref;
}
export interface PrimitiveStep {
 operator: "SPLIT" | "CONCAT"; args: {position?: number};
 input_state_ref: Ref; other_state_ref: Ref | null;
 output_state_refs: Ref[]; input_word_hash: Ref; output_word_hashes: Ref[];
}
export interface RoleTree {
 range: [number,number]; tokens: string[]; input_state_ref: Ref;
 kind: "EPS_BASE" | "RULE";
 roles: {role: "OPEN" | "CLOSE"; position:number; token:string; state_ref:Ref}[];
 children: RoleTree[]; trace: PrimitiveStep[]; allocation: number[];
 measure: {parent:number; children:number[]}; reconstructed_tokens:string[];
}
interface ProofBinding {
 schema:"finite-role-certificate/1"; program_digest:Ref; record_ref:Ref;
 source_sha256:Ref; scope_digest:Ref; input_state:WordState;
}
export type RoleCertificate = ProofBinding & (
 {status:"UNKNOWN"; reason:string} |
 {status:"DECIDED"; decision:boolean;
  cells:{range:[number,number]; value:boolean; allocation:number[]|null}[];
  tree:RoleTree|null; states:Record<Ref,WordState>; work:{cells:number;split_trials:number}}
);
export interface VerifyQueryArguments {project:string;run_id:Ref;feature_id:string;query_id:string;certificate?:RoleCertificate;}
