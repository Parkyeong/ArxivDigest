import dataclasses
import logging
import math
import os
import sys
import time
from typing import Optional, Sequence, Union

import openai
from openai import OpenAI
import tqdm
import copy


_client = None


def _get_client():
    global _client
    if _client is None:
        api_key = os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            raise RuntimeError("OPENROUTER_API_KEY not set.")
        _client = OpenAI(
            api_key=api_key,
            base_url="https://openrouter.ai/api/v1",
        )
    return _client


@dataclasses.dataclass
class OpenAIDecodingArguments(object):
    max_tokens: int = 1800
    temperature: float = 0.2
    top_p: float = 1.0
    n: int = 1
    stream: bool = False
    stop: Optional[Sequence[str]] = None
    presence_penalty: float = 0.0
    frequency_penalty: float = 0.0


def openai_completion(
    prompts,
    decoding_args: OpenAIDecodingArguments,
    model_name="openai/gpt-4o-mini",
    sleep_time=2,
    batch_size=1,
    max_instances=sys.maxsize,
    max_batches=sys.maxsize,
    return_text=False,
    **decoding_kwargs,
):
    client = _get_client()
    is_single_prompt = isinstance(prompts, (str, dict))
    if is_single_prompt:
        prompts = [prompts]

    if max_batches < sys.maxsize:
        logging.warning(
            "`max_batches` will be deprecated in the future, please use `max_instances` instead."
        )
        max_instances = max_batches * batch_size

    prompts = prompts[:max_instances]
    num_prompts = len(prompts)
    prompt_batches = [
        prompts[batch_id * batch_size : (batch_id + 1) * batch_size]
        for batch_id in range(int(math.ceil(num_prompts / batch_size)))
    ]

    completions = []
    for batch_id, prompt_batch in enumerate(prompt_batches):
        batch_decoding_args = copy.deepcopy(decoding_args)

        backoff = 3

        while True:
            try:
                shared_kwargs = dict(
                    model=model_name,
                    **batch_decoding_args.__dict__,
                    **decoding_kwargs,
                )
                completion_batch = client.chat.completions.create(
                    messages=[
                        {"role": "system", "content": "You are a helpful assistant."},
                        {"role": "user", "content": prompt_batch[0]},
                    ],
                    **shared_kwargs,
                )
                total_tokens = completion_batch.usage.total_tokens if completion_batch.usage else 0
                for choice in completion_batch.choices:
                    completions.append({
                        "message": {"content": choice.message.content},
                        "total_tokens": total_tokens,
                        "text": choice.message.content,
                    })
                break
            except openai.OpenAIError as e:
                logging.warning(f"OpenAIError: {e}.")
                if "Please reduce your prompt" in str(e):
                    batch_decoding_args.max_tokens = int(batch_decoding_args.max_tokens * 0.8)
                    logging.warning(f"Reducing target length to {batch_decoding_args.max_tokens}, Retrying...")
                elif not backoff:
                    logging.error("Hit too many failures, exiting")
                    raise e
                else:
                    backoff -= 1
                    logging.warning("Hit request rate limit; retrying...")
                    time.sleep(sleep_time)

    if return_text:
        completions = [c["text"] for c in completions]
    if decoding_args.n > 1:
        completions = [completions[i : i + decoding_args.n] for i in range(0, len(completions), decoding_args.n)]
    if is_single_prompt:
        (completions,) = completions
    return completions


def write_ans_to_file(ans_data, file_prefix, output_dir="./output"):
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    filename = os.path.join(output_dir, file_prefix + ".txt")
    with open(filename, "w") as f:
        for ans in ans_data:
            f.write(ans + "\n")
