import os
import torch
import requests
from typing import List, Dict, Any, Optional

class MistralEngine:
    def __init__(self, mode: str = "api", model_id: str = "mistral-tiny", device: str = None):
        """
        mode: 'api' for remote inference (free/lite), 'local' for Transformers logic.
        """
        self.mode = mode or os.environ.get("LLM_MODE", "api")
        self.api_key = os.environ.get("MISTRAL_API_KEY")
        self.model_id = model_id
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.tokenizer = None
        self.model = None
        self._pipeline = None

    def load_model(self):
        """Loads the model and tokenizer."""
        # In a real high-volume scenario, we might use vLLM or TGI instead of Transformers directly.
        # Here we use Transformers for architectural demonstration.
        self.tokenizer = AutoTokenizer.from_pretrained(self.model_id)
        self.model = AutoModelForCausalLM.from_pretrained(
            self.model_id,
            torch_dtype=torch.float16 if self.device == "cuda" else torch.float32,
            device_map="auto" if self.device == "cuda" else None
        )
        self._pipeline = pipeline(
            "text-generation",
            model=self.model,
            tokenizer=self.tokenizer,
            device_map="auto" if self.device == "cuda" else None
        )

    def generate(self, prompt: str, max_new_tokens: int = 512, temperature: float = 0.7) -> str:
        if self.mode == "api":
            return self._generate_api(prompt, max_new_tokens, temperature)
        
        if not self._pipeline:
            self.load_model()
        
        messages = [
            {"role": "user", "content": prompt}
        ]
        
        # Using chat template if available
        encodeds = self.tokenizer.apply_chat_template(messages, return_tensors="pt")
        model_inputs = encodeds.to(self.device)

        generated_ids = self.model.generate(
            model_inputs, 
            max_new_tokens=max_new_tokens, 
            do_sample=True,
            temperature=temperature,
            pad_token_id=self.tokenizer.eos_token_id
        )
        
        decoded = self.tokenizer.batch_decode(generated_ids)
        # Extract only the assistant's response
        response = decoded[0].split("[/INST]")[-1].replace("</s>", "").strip()
        return response

    def _generate_api(self, prompt: str, max_tokens: int, temp: float) -> str:
        """Calls Mistral AI API for inference."""
        if not self.api_key:
            raise Exception("MISTRAL_API_KEY environment variable is missing.")
            
        url = "https://api.mistral.ai/v1/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
        data = {
            "model": self.model_id,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "temperature": temp
        }
        
        response = requests.post(url, headers=headers, json=data)
        response.raise_for_status()
        return response.json()['choices'][0]['message']['content'].strip()

    def get_structured_output(self, prompt: str, schema_description: str) -> str:
        """Extends generate to enforce JSON-like structure via prompting."""
        structured_prompt = f"{prompt}\n\nPlease respond strictly in valid JSON format following this schema: {schema_description}"
        return self.generate(structured_prompt)
