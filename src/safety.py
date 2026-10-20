"""Conservative scope routing, not a medical classifier or a safety guarantee."""
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class ScopeDecision:
    route: str
    reason: str
    response: str = ''
    policy_url: str | None = None


def classify_request(question):
    text = re.sub(r'\s+', ' ', question.casefold()).strip()
    if not text:
        return ScopeDecision('insufficient_evidence', 'empty_question', 'Please enter a research question.')
    chest = re.search(r'chest (pain|pressure|tightness)|pressure (in|on) my chest', text)
    current = re.search(r'\bi (have|feel|am)|\bmy\b|keep|continue|through|right now|finish', text)
    if chest and current:
        return ScopeDecision('urgent', 'urgent_symptoms',
            'Stop exercising and seek emergency help now. In the US call 911; elsewhere call your local emergency number. This assistant cannot assess symptoms or decide that you are safe.',
            'https://www.nhlbi.nih.gov/health/heart-attack/symptoms')
    if re.search(r'dehydrat|starvation|starve|purging|purge|steroid|crash diet|lose .* (fast|overnight)|extreme.*weight loss', text):
        return ScopeDecision('out_of_scope', 'dangerous_plan',
            'I cannot provide dangerous weight-loss or drug protocols. I can help you research general adult activity and food habits from reviewed sources.')
    if re.search(r'creatine|supplement|pre.?workout|fat burner|protein powder', text):
        return ScopeDecision('out_of_scope', 'supplement_advice',
            'The reviewed evidence collection does not support supplement brands, personal recommendations or dosing. Discuss personal use with a qualified healthcare professional.',
            'https://ods.od.nih.gov/factsheets/WYNTK-Consumer/')
    medical = re.search(r'kidney|diabet|pregnan|insulin|medication|\bchild\b|\bteen\b|blood test|lab result|blood pressure', text)
    planning = re.search(r'my|\bi have\b|plan|target|calculate|treat|dose|should i|interpret', text)
    if medical and planning:
        return ScopeDecision('out_of_scope', 'medical_nutrition_or_assessment',
            'I cannot interpret personal medical data or prescribe nutrition for a condition, medication, pregnancy or child. Please discuss that with a qualified healthcare professional. General adult education is available.')
    request = re.search(r'diagnose|what (condition|disease|injury)|is my .* (injured|torn)|rehab|rehabilitat|medicine|prescrib|dose|medical clearance|treatment plan|why does my .*hurt|my .* (hurts|pain)', text)
    if request:
        return ScopeDecision('out_of_scope', 'diagnosis_or_treatment',
            'I cannot diagnose symptoms, choose medicine, prescribe rehabilitation or provide medical clearance. A qualified healthcare professional can assess your situation. I can explain general research without making a personal medical decision.')
    personal = re.search(r'\b(my|me)\b|\bshould i\b|\bfor me\b|personaliz|individuali', text)
    nutrition = re.search(r'calori|\bmacros?\b|macronutrient|\bprotein\b|meal plan|diet plan', text)
    target = re.search(r'calculate|target|deficit|plan|prescrib|how (many|much)|should i (eat|consume)|recommend', text)
    workout = re.search(r'workout|exercise|training', text)
    if personal and target and (nutrition or (workout and re.search(r'plan|routine|program', text))):
        return ScopeDecision('out_of_scope', 'personal_prescription',
            'I cannot prescribe a personal calorie, macronutrient or workout plan. I can explain the general guidance and study findings in the reviewed collection. Your logged records are observations, not a basis for personal prescriptions.')
    return ScopeDecision('allowed', 'general_adult_education')
