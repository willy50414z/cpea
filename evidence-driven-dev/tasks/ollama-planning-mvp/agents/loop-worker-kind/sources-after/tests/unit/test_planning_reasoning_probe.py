from evaluations.planning_reasoning_probe import capture_response, failure_ids


def test_capture_preserves_summary_and_distinguishes_reasoning_tokens():
    raw = {'id':'r1', 'status':'completed', 'output':[
        {'type':'reasoning','summary':[{'type':'summary_text','text':'A brief decision summary.'}]},
        {'type':'message','content':[{'type':'output_text','text':'{"status":"ready"}'}]}],
        'usage':{'input_tokens':9,'output_tokens':12,'output_tokens_details':{'reasoning_tokens':7}}}
    result = capture_response(raw)
    assert result['output_text'] == '{"status":"ready"}'
    assert result['reasoning_summary'] == ['A brief decision summary.']
    assert result['reasoning_summary_status'] == 'available'
    assert result['reasoning_tokens'] == 7


def test_missing_summary_is_not_fabricated_from_answer_or_token_count():
    result = capture_response({'status':'completed','output':[
        {'type':'reasoning','summary':[]},
        {'type':'message','content':[{'type':'output_text','text':'an answer'}]}],
        'usage':{'output_tokens_details':{'reasoning_tokens':18}}})
    assert result['reasoning_summary'] == []
    assert result['reasoning_summary_status'] == 'not_returned'
    assert result['reasoning_tokens'] == 18


def test_selects_only_failed_candidate_cases_once_in_original_order():
    review = {'reviews':[
        {'case_id':'a','arm':'v3','first_pass_semantically_safe_ready':False},
        {'case_id':'a','arm':'B1','first_pass_semantically_safe_ready':True},
        {'case_id':'b','arm':'B1','first_pass_semantically_safe_ready':False},
        {'case_id':'c','arm':'B1','first_pass_semantically_safe_ready':False}]}
    assert failure_ids(review) == ['b','c']
