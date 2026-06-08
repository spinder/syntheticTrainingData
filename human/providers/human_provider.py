counter = 0

def call_api(prompt, options, context):
    global counter

    answers = ["true", "false"]
    answer = answers[counter % 2]
    counter += 1

    return {
        "output": answer
    }
