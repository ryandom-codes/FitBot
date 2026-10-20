"""One local generation responsibility with a typed result."""
def answer_question(client, question, evidence, personal_summary=None, untrusted_notes=''):
    return client.generate(question, evidence, personal_summary, untrusted_notes)
