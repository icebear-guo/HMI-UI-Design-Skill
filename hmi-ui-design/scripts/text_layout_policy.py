"""A serializable multi-text child collection is not proof of native layout."""
def validate_text_layout(control):
    texts=control.get('texts',[])
    states=[s['id'] for s in control.get('states',[])] or [None]
    counts=[sum(t.get('text_owner')=='component' and t.get('state') in (None,state) for t in texts) for state in states]
    if max(counts,default=0)<=1:
        return
    evidence=control.get('native_multi_text_layout_verified')
    if not (isinstance(evidence,dict)
            and evidence.get('result')=='passed_in_native_editor'
            and isinstance(evidence.get('software_version'),str) and evidence['software_version'].strip()
            and isinstance(evidence.get('evidence'),str) and evidence['evidence'].strip()):
        raise ValueError('Multiple simultaneous native text children need actual native layout evidence; default to independent labels/value controls and a layout picture: '+control['id'])
