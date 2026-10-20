"""Local Streamlit demo. Research evidence and private observations stay distinct."""
from datetime import date
import json
import pandas as pd
import streamlit as st
from src.config import load_settings
from src.storage import (init_db,save_profile,list_profiles,save_checkin,save_lift,
                         get_history,delete_profile,delete_lift,export_history)
from src.progress import summarize_history,weight_to_kg,height_to_cm

st.set_page_config(page_title='Fitness Research Assistant',page_icon='📖',layout='centered')
st.title('Fitness Research & Tracking Assistant')
st.caption('V2.1 · Created by Ryan Dominguez')
st.caption('General adult education from reviewed sources, plus your own logged observations.')
st.info('This is a student project, not medical care. It cannot diagnose, prescribe treatment or provide medical nutrition or supplement plans. For urgent symptoms, seek emergency help.')

try:
    settings = load_settings()
except ValueError as exc:
    st.error(str(exc)); st.stop()

demo = st.sidebar.toggle('Use synthetic demo records',value=True)
db = settings.private_dir / 'synthetic_demo.db' if demo else settings.database_path
if demo and not db.exists():
    payload = json.loads((settings.project_root/'data'/'demo_history.json').read_text(encoding='utf-8'))
    if payload.get('synthetic') is not True:
        st.error('Demo data is not marked synthetic.'); st.stop()
    init_db(db)
    pid = save_profile(db,payload['profile'])
    for row in payload['checkins']: save_checkin(db,pid,row)
    for row in payload['lifts']: save_lift(db,pid,row)
else:
    init_db(db)
st.sidebar.caption('Synthetic example only.' if demo else 'Private records stay in an external SQLite file. This local app has no authentication or encryption.')
profiles = list_profiles(db)
profile = st.sidebar.selectbox('Local profile',profiles,format_func=lambda p:p['label'] or f"Profile {p['id']}") if profiles else None
view = st.sidebar.radio('View',['Research','Profile','Check-in','Progress'])


@st.cache_resource
def pipeline(method, source_hash, model, embedding_model, host, private_dir):
    from agents.ingestion_agent import ingest
    from agents.coordinator import Coordinator
    from src.llm import LocalModelClient
    from src.retrieval import build_index
    client = LocalModelClient(settings)
    chunks = ingest(settings.project_root/'data'/'sources.json')
    index = build_index(chunks,client,settings.cache_dir) if method == 'vector' else None
    return Coordinator(chunks,client,index)


if view == 'Profile':
    st.subheader('A few optional details')
    st.write('Use a nickname, not identifying or medical information. Height and weight are optional; this app does not calculate personal diet prescriptions.')
    edit = st.checkbox('Edit selected profile',disabled=profile is None)
    current = profile if edit else {}
    height_unit = st.selectbox('Height unit',['cm','in'])
    with st.form('profile'):
        label = st.text_input('Profile label',value=current.get('label',''),max_chars=80)
        goals = st.text_input('General goals',value=current.get('goals',''),max_chars=300)
        experience = st.selectbox('Experience',['New to exercise','Some experience','Experienced'],index=['New to exercise','Some experience','Experienced'].index(current['experience']) if current.get('experience') in ['New to exercise','Some experience','Experienced'] else 0)
        equipment = st.text_input('Available equipment',value=current.get('equipment',''),max_chars=300)
        available = st.slider('Available days per week',0,7,int(current.get('available_days',3)))
        height = st.number_input('Optional height (0 means not entered)',min_value=0.0,value=float(current.get('height_cm') or 0)/(2.54 if height_unit=='in' else 1),step=1.0)
        if st.form_submit_button('Save profile'):
            values = dict(label=label,goals=goals,experience=experience,equipment=equipment,available_days=available,height_cm=height_to_cm(height,height_unit) if height else None)
            if edit: values['id']=profile['id']
            save_profile(db,values); st.success('Saved.'); st.rerun()
    if profile:
        st.download_button('Export selected profile as JSON',export_history(db,profile['id']),file_name='fitness_history.json',mime='application/json')
        confirm = st.checkbox('Delete this profile and all its records')
        if st.button('Delete profile',disabled=not confirm):
            delete_profile(db,profile['id']); st.rerun()

elif view == 'Check-in':
    if not profile: st.info('Create a local profile first.'); st.stop()
    st.subheader('Daily check-in')
    st.caption('Saving the same date replaces that check-in. Leave unknown values blank; a recorded zero remains zero.')
    history = get_history(db,profile['id'])
    day = st.date_input('Date',value=date.today(),max_value=date.today())
    prior = next((r for r in history['checkins'] if r['date']==day.isoformat()),{})
    unit = st.selectbox('Weight unit',['kg','lb'])
    prior_weight=prior.get('weight_kg')
    with st.form('checkin'):
        weight = st.number_input('Body weight (optional)',min_value=0.0,value=prior_weight/(0.45359237 if unit=='lb' else 1) if prior_weight is not None else None,step=0.1)
        cardio = st.number_input('Logged cardio minutes (optional)',min_value=0.0,value=prior.get('cardio_minutes'),step=1.0)
        sleep = st.number_input('Sleep hours (optional)',min_value=0.0,max_value=24.0,value=prior.get('sleep_hours'),step=0.5)
        notes = st.text_area('Optional notes—avoid medical or identifying details',value=prior.get('notes') or '',max_chars=1000)
        if st.form_submit_button('Save check-in'):
            save_checkin(db,profile['id'],dict(date=day.isoformat(),weight_kg=weight_to_kg(weight,unit),cardio_minutes=cardio,sleep_hours=sleep,notes=notes))
            st.success('Check-in saved.'); st.rerun()
    st.subheader('Lift entry')
    selected = st.selectbox('Add or edit a lift',[None]+history['lifts'],format_func=lambda r:'New entry' if r is None else f"{r['date']} • {r['exercise']} • #{r['id']}")
    values = selected or {}
    load_unit = st.selectbox('Load unit',['kg','lb'])
    with st.form('lift'):
        lift_date = st.date_input('Lift date',value=date.fromisoformat(values['date']) if selected else day,max_value=date.today())
        exercise = st.text_input('Exercise and variant',value=values.get('exercise',''),max_chars=100)
        sets = st.number_input('Sets',min_value=0,value=int(values.get('sets',3)),step=1)
        reps = st.number_input('Reps per set',min_value=0,value=int(values.get('reps',8)),step=1)
        load = st.number_input('External load',min_value=0.0,value=float(values.get('load_kg',0))/(0.45359237 if load_unit=='lb' else 1),step=0.5)
        if st.form_submit_button('Save lift'):
            row=dict(date=lift_date.isoformat(),exercise=exercise,sets=sets,reps=reps,load_kg=weight_to_kg(load,load_unit))
            if selected: row['id']=selected['id']
            try: save_lift(db,profile['id'],row); st.success('Lift saved.'); st.rerun()
            except ValueError as exc: st.error(str(exc))
    if selected and st.button('Delete selected lift'):
        delete_lift(db,profile['id'],selected['id']); st.rerun()

elif view == 'Progress':
    if not profile: st.info('Create a local profile first.'); st.stop()
    history=get_history(db,profile['id']); summary=summarize_history(history)
    st.subheader('Your logged observations')
    a,b,c=st.columns(3)
    a.metric('Check-in days',summary['checkin_days'])
    b.metric('Logged cardio minutes',summary['total_logged_cardio_minutes'] if summary['cardio_observed_days'] else 'Not recorded')
    c.metric('Weight measurements',summary['weight_measurements'])
    if summary['weight_change_kg'] is not None:
        st.write(f"Recorded weight change: {summary['weight_change_kg']:+.2f} kg between {summary['weight_start_date']} and {summary['weight_end_date']}.")
    if history['checkins']:
        frame=pd.DataFrame(history['checkins']).set_index('date')
        for column,title in [('weight_kg','Recorded body weight (kg)'),('cardio_minutes','Recorded cardio minutes')]:
            if frame[column].notna().any(): st.write(title); st.line_chart(frame[[column]])
        st.dataframe(frame[['weight_kg','cardio_minutes','sleep_hours']],use_container_width=True)
    if summary['lifts_by_exercise']:
        st.write('Logged lifting volume by exercise (kg × reps)')
        st.dataframe(pd.DataFrame(summary['lifts_by_exercise']).T,use_container_width=True)
    st.caption(summary['limitations'])
    st.download_button('Export selected history',export_history(db,profile['id']),file_name='fitness_history.json',mime='application/json')

else:
    st.subheader('Ask the reviewed collection')
    st.caption('Examples: How does the talk test work? What do the resistance-training studies include and exclude? What does a serving size mean?')
    method_label=st.selectbox('Retrieval method',['Vector embeddings','Keyword baseline (BM25)'])
    method='vector' if method_label.startswith('Vector') else 'keyword'
    topic=st.selectbox('Collection',['All','exercise','strength','cardio','nutrition','sleep'],key='research_collection')
    def fill_example():
        example=st.session_state['example_question']
        if example!='Choose a question':
            st.session_state['question_input']=example
            st.session_state['research_collection']='All'
    st.selectbox('Try an example',['Choose a question','What is the talk test?',
        'How much aerobic activity do adults generally need?',
        'What are some sleep habits the CDC recommends?',
        'What does a serving size mean?',
        'What do the included resistance-training studies say, and what are their limitations?'],
        key='example_question',on_change=fill_example)
    question=st.text_area('Research question',max_chars=2000,key='question_input')
    if st.button('Find evidence and answer',type='primary',disabled=not question.strip()):
        st.session_state.pop('research_result',None)
        from src.safety import classify_request
        from agents.coordinator import Coordinator
        decision=classify_request(question)
        try:
            with st.spinner('Checking scope, retrieving evidence and running the local model…'):
                if decision.route!='allowed':
                    result=Coordinator([],None).research(question,method)
                else:
                    import hashlib
                    fingerprint=hashlib.sha256((settings.project_root/'data'/'sources.json').read_bytes()).hexdigest()
                    result=pipeline(method,fingerprint,settings.model,settings.embedding_model,settings.host,str(settings.private_dir)).research(question,method,None if topic=='All' else topic)
            st.session_state['research_result']=result.model_dump(mode='json')
        except Exception as exc:
            st.error(f'Local research could not start: {type(exc).__name__}: {exc}. Check that Ollama is running and both models are installed.')
    stored=st.session_state.get('research_result')
    if stored:
        display_result=stored.copy()
        st.caption(f"Last question: {stored['question']}")
        if stored['error']: st.error('The request failed; no invented fallback answer was returned. '+stored['error'])
        answer=stored['answer']; checks=stored['verification']
        if checks and checks['flags'] and stored['route']=='allowed':
            st.error('The response failed a safety or evidence check and is withheld. Try a general evidence question. The failure remains available for project evaluation.')
            answer=None
            display_result['answer']=None
            display_result['withheld_reason']='Generated output failed an evidence or scope check.'
        if answer:
            st.write(f"**Status:** {answer['status'].replace('_',' ')}")
            st.markdown('**Answer**')
            if not answer['key_points']:
                st.write(answer['answer'])
            for point in answer['key_points']:
                st.write('• '+point['text'])
                sources={item['chunk']['id']:item['chunk'] for item in stored['retrieved']}
                links=[f"[{sources[c]['title']}]({sources[c]['url']})" if c in sources else c for c in point['citations']]
                st.caption('Citations: '+', '.join(links))
            if checks:
                if checks['status']=='flagged': st.warning('Verification flags: '+', '.join(checks['flags'])+'. Treat this answer as unverified.')
                elif checks['status']=='policy_response': st.caption('Fixed scope response; the model was not called.')
                else: st.caption('Verification: '+checks['status'].replace('_',' ')+'. Exact quotes and citation IDs checked; relevance and completeness still need review.')
            if answer['caveats']:
                with st.expander('Population limits and caveats'):
                    for caveat in answer['caveats']: st.write(caveat)
            for followup in answer['follow_up_questions']: st.write('Follow-up: '+followup)
        for item in stored['retrieved']:
            chunk=item['chunk']
            with st.expander(f"{chunk['title']} — {chunk['section']}"):
                st.markdown(f"[Original source]({chunk['url']})")
                st.caption(f"{chunk['id']} • {chunk['evidence_type']} • {chunk['date_label']}: {chunk['published_date'] or 'not established'} • snapshot: {chunk['accessed_date'] or 'not established'}")
                st.write(chunk['text'])
                if chunk['scope']: st.caption('Scope: '+chunk['scope'])
                if chunk['limitations']: st.caption('Limitations: '+chunk['limitations'])
        if stored['route']=='urgent': st.markdown('[Emergency guidance: NHLBI](https://www.nhlbi.nih.gov/health/heart-attack/symptoms)')
        with st.expander('Structured result'): st.json(display_result)
