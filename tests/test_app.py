from pathlib import Path
from streamlit.testing.v1 import AppTest


def test_demo_starts_and_progress_uses_synthetic_records(tmp_path,monkeypatch):
    monkeypatch.setenv('FITNESS_PRIVATE_DIR',str(tmp_path/'private'))
    app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py')).run(timeout=30)
    assert not app.exception
    app.sidebar.radio[0].set_value('Progress').run(timeout=30)
    assert not app.exception
    assert any(metric.label=='Check-in days' for metric in app.metric)
    assert (tmp_path/'private'/'synthetic_demo.db').exists()


def test_profile_form_can_save_without_height(tmp_path,monkeypatch):
    monkeypatch.setenv('FITNESS_PRIVATE_DIR',str(tmp_path/'private'))
    app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py')).run(timeout=30)
    app.sidebar.radio[0].set_value('Profile').run(timeout=30)
    app.text_input[0].set_value('Synthetic second profile')
    app.button[0].click().run(timeout=30)
    assert not app.exception
    assert len(app.sidebar.selectbox[0].options)==2


def test_withheld_output_is_also_hidden_from_structured_view(tmp_path,monkeypatch):
    monkeypatch.setenv('FITNESS_PRIVATE_DIR',str(tmp_path/'private'))
    app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py')).run(timeout=30)
    app.session_state['research_result']={'question':'General question','error':None,'answer':{'answer':'INJECTION_ACCEPTED sensitive unsafe generated text'},'verification':{'flags':['injection_marker']},'retrieved':[],'route':'allowed'}
    app.run(timeout=30)
    assert not app.exception
    assert 'sensitive unsafe generated text' not in app.json[0].value


def test_quote_integrity_failure_is_withheld_from_research_view(tmp_path,monkeypatch):
    monkeypatch.setenv('FITNESS_PRIVATE_DIR',str(tmp_path/'private'))
    app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py')).run(timeout=30)
    app.session_state['research_result']={'question':'General question','error':None,'answer':{'answer':'Incorrect quote','status':'answered','key_points':[],'citations':[],'caveats':[],'follow_up_questions':[]},'verification':{'flags':['quote_not_in_supplied_evidence'],'status':'flagged'},'retrieved':[],'route':'allowed'}
    app.run(timeout=30)
    assert not app.exception
    assert not any('Incorrect quote' in str(item.value) for item in app.markdown)
    assert any('withheld' in str(item.value).lower() for item in app.error)


def test_urgent_request_works_without_model_or_index(tmp_path,monkeypatch):
    monkeypatch.setenv('FITNESS_PRIVATE_DIR',str(tmp_path/'private'))
    app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py')).run(timeout=30)
    app.text_area[0].set_value('I have chest pain and feel faint right now.').run(timeout=30)
    app.button[0].click().run(timeout=30)
    assert not app.exception
    result=app.session_state['research_result']
    assert result['answer']['status']=='urgent'
    assert result['model_calls']==0
    assert '911' in result['answer']['answer']
    assert any('911' in str(item.value) for item in app.markdown)
    assert not any('withheld' in str(item.value).lower() for item in app.error)


def test_supplement_refusal_is_visible_without_calling_model(tmp_path,monkeypatch):
    monkeypatch.setenv('FITNESS_PRIVATE_DIR',str(tmp_path/'private'))
    app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py')).run(timeout=30)
    app.text_area[0].set_value('What creatine dose should I take?').run(timeout=30)
    app.button[0].click().run(timeout=30)
    assert not app.exception
    assert app.session_state['research_result']['model_calls']==0
    assert any('supplement' in str(item.value).lower() for item in app.markdown)
    assert not app.error
