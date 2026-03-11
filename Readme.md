# Accessbility Checker Backend API

This is an mimic of a11y of axe-core + lighthouse + visual accessbility test

## Installation
```
poetry install
```

## Rules to cover

----------------------------


## Perceivable 

- 1.1.1 Non Text Content
  - Check alt text presence 
  - if the image is functional check the alt text represent the accessible name of functionality (regex)
  - if the text is present over image it should reflect in alt text (regex, nltk)
  

- 1.2.1 Time Based Media 
  - Audio only video only (Prerecorded) (Transcript must match with description of the video or audio)


- 1.2.2 Captions (Prerecorded)
  - Have to check captions accuracy with the transcript


- 1.2.3 Audio Descriptions or Media alternative (Prerecorded)
  - Verify audio descriptions accurately describe visual content


- 1.2.4. Live captions 
  - Presence of live captions 


- 1.2.5 Audio Descriptions Prerecorded 
  - Evaluate Quality and Accuracy of Audio Descriptions 


- 2.1.1 Keyboard 
  - Check if custom interactive elements have tab index or role and if access keys are unique 
  - it should check drag drop , custom widgets and complex interractions 


- 2.2.2 Pause, Stop, Hide
  - Check all css animations and js whether the control is present for moving contents 



## Output format

------------------------------------------------


| Total Passed | Total Failed | Total Warnings |
|--------------|--------------|----------------|
| 20%          | 70%          | 10%            |

| Violations        | Suggesstion Fix | Level | Rule  | Element      |
|-------------------|-----------------|-------|-------|--------------|
| Missing Alt text  | add alt text    | A     | 1.1.1 | <img src=""> |
...




