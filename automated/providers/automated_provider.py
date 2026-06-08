#def call_api(prompt, options, context):
#    # TODO: replace with actual rule-based or script-driven evaluation logic
#    return {
#        "output": "true"
#    }

counter = 0

def call_api(prompt, options, context):
    global counter

    answers = ["true", "false"]
    answer = answers[counter % 2]
#    answer = answers[counter % 1]
    counter += 1

    return {
        "output": answer
    }
