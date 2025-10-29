# ECE 461/30861 - Team 17 - PHASE 2

Group List (Name, GitHub User):
1. Alex Piet (alex42p)
2. George Meng (georgemeng915)
3. Joey D'Alessandro (joeyd514)

## TODO:
  - Implement Phase 2 AWS stuff
    - start with API endpoints in `src/app.py`
  - Improve scores to match our original ones
  - Add test suite back

## Accomplishments
  - Restructured the repo including: 
    - deleted useless shit
    - changed the folder structure
    - removed all tests
    - temporarily fixed CI/CD pipeline
  - Fixed code entrypoint (cli.py) so that stuff actually runs when you call "./run [arg]"
  - Added Flask app skeleton code so we can start building endpoints
  - Metrics fixed:
    - License
    - Size
    - Ramp Up Time
    - Bus Factor
    - Performance Claims
    - Dataset and Code
    - Code Quality (I think?)

Performance needs to be reworked to get rid of the LLM usage - change calculation back to the original Claude design from a very early commit