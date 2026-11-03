"""Validate flow-node -> individual equipment/part atlas coverage, not aesthetic quality."""
import argparse,json
from pathlib import Path


def need(ok,message):
    if not ok:raise ValueError(message)


def source_file(root,value):
    need(isinstance(value,str) and value,'Actual editable source file required')
    path=Path(value)
    need(not path.is_absolute() and '..' not in path.parts,'Source path must remain relative to the catalog')
    resolved=(root/path).resolve()
    need(resolved.is_relative_to(root.resolve()) and resolved.is_file(),'Missing/outside source file: '+value)
    need(resolved.suffix.lower() in ('.html','.svg','.js','.mjs'), 'Keep an editable flow/atlas source, not only a flattened PNG')
    return resolved


def check(catalog,root,phase='atlas'):
    need(catalog.get('schema_version')=='1.1','Equipment catalog schema 1.1 required')
    need(catalog.get('design_revision'),'Catalog design revision required')
    flow=catalog.get('process_flow')
    need(isinstance(flow,dict),'Draw system/equipment/part flow relationships before atlas design')
    source_file(root,flow.get('source_file'))
    nodes=flow.get('nodes');edges=flow.get('connections')
    need(isinstance(nodes,list) and bool(nodes) and isinstance(edges,list),'Flow nodes and connections required')
    by={}
    for node in nodes:
        need(isinstance(node.get('id'),str) and node['id'] and node['id'] not in by,'Duplicate/missing flow node ID')
        need(node.get('level') in ('system','equipment','part') and node.get('name'),'Flow node needs name and system/equipment/part level')
        need(isinstance(node.get('ports'),list) and all(isinstance(p,str) and p for p in node['ports']) and len(set(node['ports']))==len(node['ports']),'Explicit unique flow ports required; use [] for a structural part without process ports')
        by[node['id']]=node
    need(any(n['level']=='system' for n in nodes) and any(n['level']=='equipment' for n in nodes),'Actual system and equipment nodes required')
    for node in nodes:
        parent=node.get('parent_id')
        if node['level']=='part':need(parent in by and by[parent]['level'] in ('equipment','part'),'Part must belong to its actual equipment or part assembly')
        seen={node['id']}
        while parent is not None:
            need(parent in by and parent not in seen,'Flow containment parent missing/cyclic')
            seen.add(parent);parent=by[parent].get('parent_id')
    for edge in edges:
        for node_key,port_key in [('from_node','from_port'),('to_node','to_port')]:
            node=by.get(edge.get(node_key))
            need(node is not None and edge.get(port_key) in node['ports'],'Connection refers to a missing node/port')
        need(edge.get('medium'),'Connection direction/medium must be explicit')
    required={n['id'] for n in nodes if n['level'] in ('equipment','part')}
    if phase=='flow':
        return {'status':'pass','scope':'flow_graph_integrity_only','required_atlas_nodes':sorted(required),'visual_quality':'not_authenticated'}
    equipment=catalog.get('equipment')
    need(isinstance(equipment,list) and bool(equipment),'Equipment/part atlas cannot be empty after drawing the flow diagram')
    expected_representation='refined_pseudo_3d'
    override=catalog.get('style_override')
    if override is not None:
        need(isinstance(override,dict) and override.get('representation') and override.get('user_message') and override.get('message_ref'), 'Different equipment style needs an explicit recorded user instruction')
        expected_representation=override['representation']
    mapped={};ids=set()
    for entry in equipment:
        need(isinstance(entry.get('id'),str) and entry['id'] and entry['id'] not in ids,'Duplicate/missing atlas ID');ids.add(entry['id'])
        need(entry.get('representation')==expected_representation,'Flow boxes are not final equipment/part atlas illustrations; honor only an explicit recorded style override')
        need(entry.get('item_kind') in ('equipment','part'),'Atlas item_kind required')
        source_file(root,entry.get('source_file'))
        need(entry.get('source_component_id') and entry.get('mechanical_layers'),'Individual mechanical source layers required')
        size=entry.get('design_size_px')
        need(isinstance(size,list) and len(size)==2 and all(type(v)is int and v>0 for v in size),'Atlas size required')
        references=entry.get('flow_node_ids')
        need(isinstance(references,list) and bool(references),'Atlas must reference actual equipment/part flow nodes')
        for node_id in references:
            need(node_id in required and node_id not in mapped and by[node_id]['level']==entry['item_kind'],'Atlas node reference missing, duplicated or has wrong level')
            mapped[node_id]=entry['id']
        need(all(isinstance(entry.get(k),list) for k in ('ports','states','instances','separate_indicator_layers','separate_label_layers')),'Atlas layers/ports/states/instances must be explicit arrays')
        port_ids=set()
        for port in entry['ports']:
            anchor=port.get('anchor_px')
            need(port.get('id') and port['id'] not in port_ids and isinstance(anchor,list) and len(anchor)==2 and all(type(v) in (int,float) for v in anchor),'Atlas ports require unique IDs and anchor_px')
            need(0<=anchor[0]<=size[0] and 0<=anchor[1]<=size[1],'Atlas port outside its canvas')
            port_ids.add(port['id'])
        for node_id in references:need(set(by[node_id]['ports'])<=port_ids,'Atlas omits ports declared in the flow diagram')
        need(bool(entry['states']) and bool(entry['instances']) and entry.get('prompt_or_source'),'Atlas states/instances/source required')
    need(set(mapped)==required,'Missing individual atlas items: '+str(sorted(required-set(mapped))))
    return {'status':'pass','scope':'flow_graph_and_declared_atlas_coverage','flow_nodes':len(nodes),'atlas_masters':len(equipment),
            'covered_equipment_and_parts':len(mapped),'visual_quality':'not_authenticated','final_composition':'not_checked'}


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--catalog',type=Path,required=True);ap.add_argument('--phase',choices=('flow','atlas'),default='atlas');args=ap.parse_args()
    try:
        result=check(json.loads(args.catalog.read_text(encoding='utf-8-sig')),args.catalog.resolve().parent,args.phase)
        print(json.dumps(result,ensure_ascii=False,indent=2))
    except (ValueError,KeyError,OSError,TypeError) as e:
        print(json.dumps({'status':'fail','error':str(e)},ensure_ascii=False));raise SystemExit(1)
