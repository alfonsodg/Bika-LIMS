*** Settings ***

Library          Selenium2Library  timeout=10  implicit_wait=0.2
Library          String
Resource         keywords.txt
Variables        plone/app/testing/interfaces.py
Variables        bika/lims/tests/variables.py
Suite Setup      Start browser
Suite Teardown   Close All Browsers

*** Variables ***

*** Test Cases ***

Create Client
    Log in   test_labmanager1   test_labmanager1
    Go to                       ${PLONEURL}/clients

    Click link                  Add
    Wait Until Page Contains Element  Name

    Input Text                  Name                    Robot Test Client
    Input Text                  ClientID                ROBOTTEST
    Input Text                  TaxNumber               98765A
    Input Text                  Phone                   011 3245679
    Input Text                  Fax                     011 3245678
    Input Text                  EmailAddress            client@example.com
    Select Checkbox             BulkDiscount
    Select Checkbox             MemberDiscountApplies

    Click link                  Address
    Select From List            PhysicalAddress.country:record     South Africa
    Select From List            PhysicalAddress.state:record       Gauteng
    Input Text                  PhysicalAddress.city               Johannesburg
    Input Text                  PhysicalAddress.zip                9000
    Input Text                  PhysicalAddress.address            Foo Street 20
    Select From List            PostalAddress.selection            PhysicalAddress
    Input Text                  PostalAddress.address              Foo Postbox 20
    Select From List            BillingAddress.selection           PostalAddress

    Click link                  Bank details
    Input Text                  AccountType             Robot Account Type
    Input Text                  AccountName             Robot Account Name
    Input Text                  AccountNumber           Robot Account Number
    Input Text                  BankName                Robot Bank Name
    Input Text                  BankBranch              Robot Bank Branch

    Click link  fieldsetlegend-preferences
    #Select From List  EmailSubject:list
    #Select From List  DefaultCategories:list
    #Select From List  RestrictedCategories:list

    Click Button  Save
    Page should contain  Changes saved.

Create Client Contact
    Log in          test_labmanager1   test_labmanager1
    Go to           ${PLONEURL}/clients/client-1
    Click link      Contacts
    Click link      Add

    Wait Until Page Contains Element  Firstname
    Input Text  Salutation            Mr
    Input Text  Firstname             Bob
    Input Text  Middleinitial         N
    Input Text  Middlename            None
    Input Text  Surname               Dobbs
    Input Text  JobTitle              Slacker
    Input Text  Department            Theological studies

    Click Link  Email Telephone Fax
    Wait Until Page Contains Element  EmailAddress
    Input Text                        EmailAddress   bob@example.com
    Input Text                        BusinessPhone  011 400 4000
    Input Text                        BusinessFax    011 500 5000
    Input Text                        HomePhone      011 600 6000
    Input Text                        MobilePhone    082 700 7000

    Click Link  Address
    Wait Until Page Contains Element  PhysicalAddress.country
    Select From List  PhysicalAddress.country:record    South Africa
    Select From List  PhysicalAddress.state:record      Gauteng
    Input Text  PhysicalAddress.city                    Johannesburg
    Input Text  PhysicalAddress.zip                     9000
    Input Text  PhysicalAddress.address                 20 Foo Road
    Select From List  PostalAddress.selection           PhysicalAddress
    Input Text  PostalAddress.address                   PO Box 20, Foo

    Click Link  Publication preference
    log  XXX Publication preferences are broken - the widgets need to make sense, and be adaptable.  WARN
    Wait Until Page Contains Element  PublicationPreference
    Select Checkbox                   AttachmentsPermitted

    Log  No archetypes-fieldname-CCContact field selected  WARN
    #Click Element  no archetypes-fieldname-CCContact

    Click Button  Save
    Page should contain  Changes saved.



*** Keywords ***

Start browser
    Open browser        ${PLONEURL}/login_form
    Set selenium speed  ${SELENIUM_SPEED}
