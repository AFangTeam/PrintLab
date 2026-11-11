from printlab import materials


def test_history_never_becomes_current_full_spool():
    baseline={'confirmed_at':'2026-10-25','initial_snapshot':[{'spool_id':1,'weight_used':0,'label_weight':1000}]}
    item=materials.inventory_items([{'id':1,'brand':'Bambu Lab','material':'PLA','label_weight':1000,'weight_used':0}],baseline)[0]
    assert item['remaining_percent']==100
    assert item['quantity_basis']=='inventory_estimate'
    assert item['actual_remaining_weight'] is None
    assert item['historical_baseline']['basis']=='historical_user_confirmation'


def test_packaging_english_and_codes_are_not_guessed():
    item=materials.inventory_items([{'id':1,'brand':'Bambu Lab','material':'PETG','subtype':'Matte','color_name':'Turquoise','material_number':'35603'}])[0]
    assert item['english_label']=='Bambu Lab PETG Matte — Turquoise'
    assert item['material_number']=='35603'
    assert 'Color not identified' in materials.english_label({'brand':'Bambu Lab','material':'PETG Matte'})


def test_rfid_manual_records_are_preserved_without_summing():
    rows=[{'id':13,'brand':'Bambu Lab','material':'PETG','subtype':'Matte','data_origin':'rfid_auto'},
          {'id':10,'brand':'Bambu Lab','material':'PETG','subtype':'Matte','color_name':'Red','data_origin':'manual'}]
    result=materials.inventory_items(rows)
    assert len(result)==2 and result[0]['possible_duplicate_ids']==[10]
    assert 'total' not in result[0]


def test_presence_bit_wins_and_identification_is_not_fabricated():
    assert materials.slot_state({'exists':False,'state':11,'tray_type':'PLA'})=='empty'
    assert materials.slot_state({'exists':True,'state':9,'tray_type':'PLA'})=='loaded'
    assert materials.slot_state({'exists':True,'state':11,'tray_type':''})=='unidentified'
    assert materials.slot_state({'exists':True,'reading':True})=='identifying'
    assert materials.slot_state({})=='unknown'


def test_slots_have_user_numbers_real_single_nozzle_route_and_invalid_remain_unknown():
    status={'id':1,'connected':True,'last_ams_update':1000,'ams_extruder_map':{'0':1},'ams':[{'id':0,'tray':[{'id':0,'exists':True,'state':11,'tray_type':'PETG','tray_sub_brands':'PETG Matte','remain':-1}]}]}
    result=materials.slot_overview(status,now=1010)
    slots=result['modules'][0]['slots']
    assert [s['slot_number'] for s in slots]==[1,2,3,4]
    assert slots[0]['reported_remaining_percent'] is None
    assert slots[0]['route']['nozzle_number']==1
    assert '左主喷嘴 1' in slots[0]['route']['text']
    assert slots[0]['diagnostics']['physical_extruder_id']==1
    assert result['fresh'] is True
    assert slots[1]['state']=='unknown'


def test_device_report_100_does_not_derive_actual_grams_and_staleness_is_explicit():
    status={'connected':True,'last_ams_update':1000,'ams':[{'id':0,'tray':[{'id':0,'state':11,'tray_type':'PLA','remain':100}]}]}
    slot=materials.slot_overview(status,now=1100)['modules'][0]['slots'][0]
    assert slot['reported_remaining_percent']==100 and slot['actual_remaining_weight'] is None
    assert slot['fresh'] is False


def test_mismatching_assignment_cannot_supply_color_or_material_number():
    status={'id':1,'connected':True,'last_ams_update':1000,'ams':[{'id':0,'tray':[{'id':0,'exists':True,'state':11,'tray_type':'PETG','tray_color':'FF0000FF'}]}]}
    assignments=[{'printer_id':1,'ams_id':0,'tray_id':0,'spool_id':2}]
    inventory=[{'id':2,'brand':'Bambu Lab','material':'PLA','color_name':'Green','material_number':'wrong'}]
    slot=materials.slot_overview(status,assignments,inventory,now=1010)['modules'][0]['slots'][0]
    assert slot['assignment_matches'] is False and slot['material_number'] is None
    assert slot['color_name'] is None and slot['spool_id'] is None


def test_private_tag_data_never_leaves_normalizer():
    item=materials.inventory_items([{'id':2,'tag_uid':'private','tray_uuid':'private','serial':'private'}])[0]
    assert all(k not in item for k in ['tag_uid','tray_uuid','serial'])


def test_unknown_color_assignment_cannot_promote_packaging_identity():
    status={'id':1,'connected':True,'last_ams_update':1000,'ams':[{'id':0,'tray':[{'id':0,'exists':True,'state':11,'tray_type':'PETG','tray_color':'D6001CFF'}]}]}
    assignments=[{'printer_id':1,'ams_id':0,'tray_id':0,'spool_id':2}]
    inventory=[{'id':2,'brand':'Bambu Lab','material':'PETG','subtype':'Matte','color_name':'Turquoise','material_number':'35603'}]
    slot=materials.slot_overview(status,assignments,inventory,now=1010)['modules'][0]['slots'][0]
    assert not slot['assignment_matches'] and slot['color_name'] is None and slot['material_number'] is None


def test_missing_printer_identity_never_uses_another_printers_assignment():
    status={'connected':True,'last_ams_update':1000,'ams':[{'id':0,'tray':[{'id':0,'exists':True,'state':11,'tray_type':'PLA','tray_color':'FFFFFFFF'}]}]}
    assignments=[{'printer_id':2,'ams_id':0,'tray_id':0,'spool_id':2}]
    inventory=[{'id':2,'brand':'Bambu Lab','material':'PLA','color_name':'White','rgba':'FFFFFFFF'}]
    slot=materials.slot_overview(status,assignments,inventory,now=1010)['modules'][0]['slots'][0]
    assert not slot['assignment_matches'] and slot['spool_id'] is None


def test_exact_rgba_limits_unknown_color_duplicate_candidates_without_merging():
    family={'brand':'Bambu Lab','material':'PETG','subtype':'Matte'}
    rows=[{**family,'id':13,'data_origin':'rfid_auto','rgba':'D6001CFF','color_name':None},
          {**family,'id':10,'data_origin':'manual','rgba':'#d6001cff','color_name':'Red','material_number':'35200'},
          {**family,'id':12,'data_origin':'manual','rgba':'B78659FF','color_name':'Caramel'},
          {**family,'id':5,'data_origin':'manual','rgba':'49AFCAFF','color_name':'Cyan'},
          {**family,'id':9,'data_origin':'manual','rgba':None,'color_name':'Turquoise'}]
    result=materials.inventory_items(rows)
    assert result[0]['possible_duplicate_ids']==[10,9]
    assert len(result)==5
    assert result[0].get('material_number') is None and result[0]['color_name'] is None
    # If the last manual record also has a known different RGBA it is excluded.
    rows[-1]['rgba']='54A99EFF'
    assert materials.inventory_items(rows)[0]['possible_duplicate_ids']==[10]


def test_two_ams_share_main_and_labels_survive_reordered_telemetry():
    status={'id':1,'connected':True,'last_ams_update':1000,
            'ams_extruder_map':{'0':1,'1':1},
            'ams':[{'id':1,'tray':[]},{'id':0,'tray':[]}]}
    result=materials.slot_overview(status,now=1010)
    assert [m['name'] for m in result['modules']]==['AMS B','AMS A']
    for module in result['modules']:
        for slot in module['slots']:
            assert slot['route']['nozzle_number']==1
            assert slot['route']['firmware_extruder_id']==slot['diagnostics']['physical_extruder_id']==1
    status['ams_extruder_map']={'1':0}
    result=materials.slot_overview(status,now=1010)
    assert result['modules'][0]['slots'][0]['route']['nozzle_number']==2
    assert '右辅喷嘴 2' in result['modules'][0]['slots'][0]['route']['text']
    assert result['modules'][1]['slots'][0]['route']['nozzle_number'] is None
