from openai import OpenAI
from dotenv import load_dotenv
import os
load_dotenv()


client = OpenAI(
    # defaults to os.environ.get("OPENAI_API_KEY")
    api_key=os.environ.get("CHATANYWHERE_API_KEY"),
    base_url="api.chatanywhere.org/v1"
)

def gpt_api(messages: list, model: str = "gpt-3.5-turbo"):
    completion = client.chat.completions.create(model=model, messages=messages)
    return completion.choices[0].message.content

def fast_ai(content: str):
    base_content = '''No s'accepten expressions ni paraules compostes, ni duplicats. \n
        El resultat ha de ser EXCLUSIVAMENT un objecte JSON amb una única clau 'paraules' i un array de les paraules. \n
        Sense comentaris, sense explicacions, sense text addicional.'''
    messages = [
        {"role": "system", "content": "Ets un assistent lingüístic català molt estricte amb el format."},
        {"role": "user", "content": content + base_content}
    ]
    res = gpt_api(messages, model="gpt-4o")
    return res

if __name__ == "__main__":
    concept = "felicitat"
    res = fast_ai(f"Genera una llista de 100 noms i verbs únics en català relacionades amb el concepte de '{concept}'. "
        "Totes les paraules han d'estar en la seva forma singular i ser una sola paraula.")
    print(res)
    print()
