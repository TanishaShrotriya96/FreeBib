#What
In the US, many marathon events call for volunteers and in exchange provide them with perks like discounted rates for the race. However, not all events calling for volunteer give such a perk by default. This app is intended to build a data engineering pipeline, which scrapes the web to find races across the US and filter them into the ones that do provide such perks. This is especially useful for a beginner runner who may not have the budget to afford a race. This application is aimed at reducing the barrier of entry into the world of running, by providing a platform for a new runner to find experienced runners by the volunteer route and get a free entry or discount for their initial runs.

#How

##Approach 1
The first approach taken is to use the RunSignUp open source api to pull details about races and then find more information about volunteering roles and such. The challenge encountered along this route was the lack of legal authorization required to sign up as an affiliate in order to run the GetRaces api making this a dead end. However, the code used to authenticate the initial AUTH_CALL and obtain the bearer token required for Oauth2 calls made to runsignup is added in this github repository, for future use.
The code was written with Claude Code assistant and tested using VSCode debugger. The next steps would involve creating Unit Tests and working out POST calls for the APIs available for use. 

##Approach 2
This directs to the extract.ipynb file, which is to build a web scraper and is still a work in progress.