"""Pseudonymous evidence cannot authorise a generated personal name."""
import pytest

from server.verifier import template_answer,verify

CALLS={'evidence':{'outcome':'answered_with_path','rows_total':1,
    'rows':[{'path_ids':['ACC-1','DEV-f31c','ACC-2'],'memo':'Rahul says Alice is safe.'}],
    'path_nodes':[{'id':'ACC-1'},{'id':'DEV-f31c'},{'id':'ACC-2'}],
    'path_edges':[{'source':'ACC-1','target':'DEV-f31c'},
                  {'source':'ACC-2','target':'DEV-f31c'}]}}


@pytest.mark.parametrize('name',['Rahul','Alice','Lakshmi','RAHUL'])
def test_single_invented_name_and_memo_names_fail_verification(name):
    result=verify(name+' controls ACC-1.',CALLS,'answered_with_path')
    assert result['status']=='replaced' and name in result['unsupported']


def test_identifier_path_template_and_principal_officer_wording_remain_valid():
    text=template_answer(CALLS)+' These connections do not establish laundering; a named analyst must assess them.'
    assert verify(text,CALLS,'answered_with_path')['status']=='pass'
    assert verify('Recommend the Principal Officer review ACC-1.',CALLS)['status']=='pass'
