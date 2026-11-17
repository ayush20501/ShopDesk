# ShopDesk

A support chat for a made-up online store. A team of small AI helpers answers each question.

## How it works

```
 customer question
        |
     router         decides what kind of question it is
        |
   +----+-------------------+--------------------+
   |                        |                    |
 policy                  orders               action
 (search the             (look up the         (check the rules,
  store rules)            customer's data)     prepare a request)
   |                        |                    |
   +----+-------------------+--------------------+
        |
    responder       writes the answer from what was found
        |
     checker        checks the answer, rewrites it once if wrong
        |
     answer         (a manager approves any request before it happens)
```

1. A **router** decides what the customer is asking.
2. The **policy** helper searches the store's rules.
3. The **orders** helper looks up that customer's own orders (read-only).
4. The **action** helper prepares a cancellation, return or ticket. A manager must approve it before anything changes.
5. A **responder** writes the answer, and a **checker** makes sure it matches what was found.

The chat page shows what the assistant is doing, then streams the answer.

## Safety

- The AI can only read the signed-in customer's own orders. It can never write to the database.
- Rules like return windows are plain code, not decided by the AI.
- Nothing changes until a manager approves it.

## Results

On my 75 test questions, the first version passed 79%. After fixing the problems I found, it passed 100%. I wrote the questions myself, so this is not an outside test.

## Limits

- No real login. You pick the customer from a list.
- All data is made up, and everything runs on one machine.
