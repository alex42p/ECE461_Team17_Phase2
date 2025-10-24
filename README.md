# ECE 461/30861 - Team 17 - PHASE 2

Group List (Name, GitHub User):
1. Alex Piet (alex42p)
2. George Meng (georgemeng915)
3. Joey D'Alessandro (joeyd514)

## TODO:
  - Fix the code so it doesn't suck booty (take previous implementation and improve the design a bit)
    - fix the rest of the metrics and make sure output is formatted correctly
  - Implement Phase 2 AWS stuff
  - Add MyPy checks back to CI/CD AFTER code is properly cleaned

## Accomplishments
  - Restructured the repo including: 
    - deleted useless shit
    - changed the folder structure
    - removed all tests
    - temporarily fixed CI/CD pipeline
  - Fixed code entrypoint (cli.py) so that stuff actually runs when you call "./run [arg]"
  - Metrics fixed:
    - License
    - Size
    - Ramp Up Time
    - Bus Factor

Performance needs to be reworked to get rid of the LLM usage - change calculation back to the original Claude design from a very early commit