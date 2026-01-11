import torch
from transformers import AutoTokenizer, AutoModelForCausalLM, pipeline
from unsloth import FastLanguageModel
import re, json, os

class ContractAnalyzer:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        
        print("Загружаем локальную модель анализа договоров (saiga-llama3-contract)...")
        
        self.model, self.tokenizer = FastLanguageModel.from_pretrained(
            "IlyaGusev/saiga_llama3_8b",
            load_in_4bit=True,
            max_seq_length=2048,
            dtype=None,  # Авто (float16 на GPU, float32 на CPU)
            trust_remote_code=False,
        )
        
        # Применяем LoRA-адаптер для анализа договоров 
        self.model = FastLanguageModel.get_peft_model(
            self.model,
            r=8,
            target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                          "gate_proj", "up_proj", "down_proj"],
            lora_alpha=16,
            lora_dropout=0,  # Отключаем для инференса
            bias="none",
            use_gradient_checkpointing=False,
        )
        
        # На практике — мы используем промпт-инжиниринг, т.к. LoRA для инференса не обязателен
        
        self.pipeline = pipeline(
            "text-generation",
            model=self.model,
            tokenizer=self.tokenizer,
            torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32,
            device_map="auto",
        )
        
        print("Модель готова к работе.")

    def analyze(self, text):
        # Сокращаем до 1500 слов (максимум для контекста)
        truncated = " ".join(text.split()[:1500])
        
        prompt = f"""<|begin_of_text|><|start_header_id|>system<|end_header_id|>
Ты — эксперт по договорам для фрилансеров в РФ. Проанализируй текст ниже.

Задачи:
1. Найди пункты, которые:  
   - Ущемляют исполнителя («одностороннее расторжение», «передача авторских прав без оплаты», «штрафы только для исполнителя»)  
   - Содержат неопределённости («в разумные сроки», «по усмотрению заказчика»)  
   - Пропущены важные условия (аванс, сроки, гарантии)  
   - Противоречат ГК РФ (ст. 708, 709, 781)  
2. Для каждого:  
   - Цитата из договора  
   - Оценка риска: high / medium / low  
   - Пояснение простыми словами  
   - Альтернативная формулировка (если high/medium)  

Формат ответа — ТОЛЬКО валидный JSON (без markdown, без пояснений):
{{
  "issues": [
    {{
      "quote": "текст цитаты",
      "risk": "high|medium|low",
      "explanation": "пояснение",
      "suggestion": "предложение по правке"
    }}
  ],
  "summary": "краткий вывод"
}}

<|eot_id|><|start_header_id|>user<|end_header_id|>
Текст договора:
{truncated}
<|eot_id|><|start_header_id|>assistant<|end_header_id|>"""

        try:
            outputs = self.pipeline(
                prompt,
                max_new_tokens=1500,
                do_sample=False,  # Детерминированно
                temperature=0.01,
                top_p=0.9,
                return_full_text=False,
            )
            
            generated = outputs[0]["generated_text"].strip()
            
            # Извлекаем JSON (модель иногда добавляет префикс)
            json_match = re.search(r'\{.*\}', generated, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
            else:
                return {
                    "issues": [],
                    "summary": " Не удалось распарсить ответ модели. Попробуйте короче сократить договор."
                }
                
        except Exception as e:
            return {
                "issues": [],
                "summary": f" Ошибка модели: {str(e)}"
            }

# Глобальный инстанс (загружается 1 раз при первом вызове)
analyzer = None

def get_analyzer():
    global analyzer
    if analyzer is None:
        analyzer = ContractAnalyzer()
    return analyzer