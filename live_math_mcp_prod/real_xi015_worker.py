"""Confined learner/predictor and separate raw theta evaluator; no source substitution."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import resource
import sys
import time
from real_xi015_source import load_native,native_block
from real_xi015_math import discover,predict,interpolation,binding_fingerprint


def main():
    parser=argparse.ArgumentParser();parser.add_argument('mode',choices=['learn','predict','measure'])
    parser.add_argument('--native',type=Path,required=True);parser.add_argument('--input',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--forbidden',type=Path,action='append',default=[])
    args=parser.parse_args();start=time.perf_counter_ns();cpu=time.process_time_ns();native=load_native(args.native)
    # Import the unchanged core before read confinement, without loading any truth files.
    from operational013 import LinearTransport
    from law_validation014_isolation import restrict_reads
    from real_xi015_legacy import XiTrainingFrame,Ledger
    from live_transfer006 import interpret,attend
    from live_constructive007 import interpret_constructive
    data=json.loads(args.input.read_text());isolation=None
    if args.mode!='measure':
        resource.setrlimit(resource.RLIMIT_AS,(536870912,536870912))
        isolation=restrict_reads(args.input.parent,args.forbidden)
    if args.mode=='learn':
        training=list(zip(data['A'],data['B']));model=discover(native,training,data['nodes'])
        try:
            LinearTransport.fit([data['A'][0]['value']['re'],data['A'][0]['value']['im']],[],{'observer':'actual complex theta interval'})
            core={'status':'UNEXPECTED_ACCEPT'}
        except ValueError as error:core={'status':'NO_GO_INTEGER_REPRESENTATION','reason':str(error)}
        # The exact original integer learner can preserve addresses, but that is not a value law.
        vectors=lambda r:[r['source_address']['cell'],r['source_address']['node'],r['source_address']['n'],r['exponent_sign']]
        transitions=[{'before':vectors(a),'after':vectors(b),'action':0,'history':[a['index']]} for a,b in training]
        invariant=LinearTransport.fit(vectors(data['A'][0]),transitions,{'observer':'source-address only'})
        f=data['legacy_frame'];frame=XiTrainingFrame(f['spec'],f['query'],{int(k):v for k,v in f['events'].items()},f['words'],data=f['data'],ledger=Ledger())
        left,right=f['spec']['histories']
        legacy={'I006':interpret(frame,left,right),'T006':attend(frame),'I007':interpret_constructive(frame,left,right)}
        output={'model':model,'unchanged013_value_attempt':core,'unchanged013_address_law':invariant.artifact(),'unchanged_I_T':legacy,
                'initial_data_sha256':data['sha256'],'source_expression_supplied_not_discovered':True}
    elif args.mode=='predict':
        # Model construction has ended; only public anchor inputs for new addresses arrive here.
        model=data['model'];results=[]
        if model['status']!='LAW_CANDIDATE':raise ValueError('MISSING_SOURCE_LAW_CANDIDATE')
        for h in data['test_h']:
            for a,b in zip(data['A'],data['B']):
                identity={'source_address':a['source_address'],'origin_id':a['origin_id'],'h':h,'t':data['t'],
                          'observer':'native-complex-interval','version':1,'definition_sha256':data['definition_sha256']}
                node=data['nodes'][str(a['source_address']['cell']*8+a['source_address']['node'])]
                results.append({'index':a['index'],'binding':identity,'fingerprint':binding_fingerprint(identity),
                    'C_source_candidate':predict(native,a,node,h),'B2_linear':interpolation(a,b,h),
                    'B2_Hermite':interpolation(a,b,h,True),'anchor_A':a['value'],'anchor_B':b['value'],
                    'phase':'prereveal prediction','proof_status':'unverified'})
        output={'predictions':results,'candidate_exp_calls':len(results),'native_theta_evaluate_calls':0,
                'new_address_inputs_are_public_anchors_not_withheld_labels':True}
    else:
        rows=native_block(native,data['nodes'],data['origins'],data['h'],data['t'])
        output={'h':data['h'],'t':data['t'],'rows':rows,'native_evaluate_calls':1,
                'source':'unchanged archival reproduce.evaluate on a validated prefix of original source atoms'}
    output['costs']={'wall_ns':time.perf_counter_ns()-start,'CPU_ns':time.process_time_ns()-cpu,
                     'peak_RSS_KiB':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}
    if isolation:output['isolation']=isolation
    args.output.write_text(json.dumps(output,ensure_ascii=False,separators=(',',':'))+'\n')


if __name__=='__main__':main()
