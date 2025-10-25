from dotenv import load_dotenv
import os
load_dotenv()



def gpt_api(messages: list, model: str = "gpt-3.5-turbo"): 
    from openai import OpenAI
    client = OpenAI(
        # defaults to os.environ.get("OPENAI_API_KEY")
        api_key=os.environ.get("CHATANYWHERE_API_KEY"),
        base_url="https://api.chatanywhere.org/v1"
    )
    completion = client.chat.completions.create(model=model, messages=messages)
    return completion.choices[0].message.content

def gemini_api(content: str, model: str = "gemini-1.5-pro"):
    from google import genai
    client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))
    response = client.models.generate_content(
        model="gemini-2.5-flash-lite", contents=content
    )
    return response.text

def fast_ai(content: str):
    base_content = '''No s'accepten expressions ni paraules compostes, ni duplicats. \n
    El resultat ha de ser EXCLUSIVAMENT un objecte JSON amb una única clau 'paraules' i un array de les paraules. \n
    Sense comentaris, sense explicacions, sense text addicional.'''

    if os.environ.get("AI_API") == "GEMINI":
        return gemini_api(content + base_content)
    else:
        messages = [
            {"role": "system", "content": "Ets un assistent lingüístic català molt estricte amb el format."},
            {"role": "user", "content": content + base_content}
        ]
        res = gpt_api(messages, model="gpt-5-mini-ca")
        return res

if __name__ == "__main__":
    concept = "felicitat"
    res = fast_ai(f"Genera una llista de 100 noms i verbs únics en català relacionades amb el concepte de '{concept}'. "
        "Totes les paraules han d'estar en la seva forma singular i ser una sola paraula.")
    print(res)
    print()
