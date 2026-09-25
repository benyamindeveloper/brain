$doc = [DocumentFormat.OpenXml.Packaging.WordprocessingDocument]::Open('D:\Barain\Project_Brain_SDS.docx', $false)
$text = $doc.MainDocumentPart.Document.Body.InnerText
$doc.Close()
$text | Out-File -FilePath 'D:\Barain\sds_content.txt' -Encoding UTF8