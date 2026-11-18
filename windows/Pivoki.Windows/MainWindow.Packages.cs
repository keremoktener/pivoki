using System.Windows;
using System.Windows.Controls;
using Pivoki.Core;

namespace Pivoki.Windows;

public sealed partial class MainWindow
{
    private OutputPackage[] cachedPackages=[];
    private HashSet<string> packageExtensions=new(StringComparer.OrdinalIgnoreCase);
    private readonly StackPanel packageHistory=new();
    private int historyVersion;

    private void StartPackageServices()
    {
        try{PackageEngine.StartWatcher(Environment.ProcessId)?.Dispose();}
        catch(Exception error)when(error is IOException or System.ComponentModel.Win32Exception)
        {L10n.SetText(status,error.Message);}
        _=RefreshPackageCacheAsync();
    }

    private async Task RefreshPackageCacheAsync()
    {
        try
        {
            var catalogTask=PackageEngine.RequestAsync(new{action="catalog"});
            var packagesTask=PackageEngine.RequestAsync(new{action="packages"});
            await Task.WhenAll(catalogTask,packagesTask);
            packageExtensions=catalogTask.Result.Inputs.ToHashSet(StringComparer.OrdinalIgnoreCase);
            cachedPackages=packagesTask.Result.Packages;
        }
        catch(Exception){cachedPackages=[];}
    }

    private void ShowStudio()=>ShowStudioTool(null);

    private void ShowStudioTool(string? tool)
    {
        try{PackageEngine.OpenStudio(tool is null?files:Array.Empty<string>(),tool);}
        catch(Exception error){MessageBox.Show(this,error.Message,"Pivoki Studio");}
    }

    private void OpenPackages(string? packageId=null,int? revision=null)
    {
        if(busy)return;
        var dialog=new PackagesWindow(this,preferences,files,packageId,revision,items=>cachedPackages=items);
        dialog.ShowDialog();
        if(LibraryVisible)_=RefreshPackageHistoryAsync();
    }

    private bool AcceptsImagePackage(IReadOnlyList<string> sources) => sources.Count>0 &&
        sources.All(path=>Directory.Exists(path) || packageExtensions.Contains(Path.GetExtension(path)));

    private IReadOnlyList<ToolChoice> PersonalWheel(string mode,IReadOnlyList<ToolChoice> standard,IReadOnlyList<string> sources)
    {
        if(sources.Count==0)return standard;
        var visible=standard.Where(choice=>!preferences.Value.HiddenWheelCommands.Contains(mode+"/"+CanonicalChoice(choice.Id))).ToList();
        if(mode=="tools" && AcceptsImagePackage(sources))
        {
            visible.InsertRange(0,cachedPackages.Where(p=>preferences.Value.PinnedPackages.Contains(p.PackageId))
                .Select(p=>new ToolChoice($"package:{p.PackageId}:{p.Revision}",p.Name,"▤")));
        }
        if(visible.Count==0)visible.Add(new("command-list","All file commands","☰"));
        return visible;
    }

    internal static string CanonicalChoice(string id)=>id switch{"crop"=>"cropImage","annotate"=>"annotateImage","mergePDFs"=>"mergePDF",_=>id};
    private bool HandlePackageChoice(string id)
    {
        if(id=="command-list"){ShowMain();ShowLibrary(false);chooseFilesButton?.Focus();return true;}
        if(!id.StartsWith("package:",StringComparison.Ordinal))return false;
        var parts=id.Split(':');
        if(parts.Length==3 && int.TryParse(parts[2],out var revision))
        {ShowMain();OpenPackages(parts[1],revision);}
        return true;
    }

    private async Task RefreshPackageHistoryAsync()
    {
        var version=++historyVersion;
        try
        {
            var jobs=(await PackageEngine.RequestAsync(new{action="history"})).Jobs;
            if(version!=historyVersion)return;
            packageHistory.Children.Clear();
            if(jobs.Length==0)return;
            var heading=new DockPanel();
            var clear=Button("Clear package history",async()=>{
                if(MessageBox.Show(this,$"{L10n.Text("Remove history records? Files stay in their folders.")} ({jobs.Length})","Pivoki",MessageBoxButton.OKCancel,MessageBoxImage.Question,MessageBoxResult.Cancel)==MessageBoxResult.OK)
                    await ChangeHistoryAsync(new{action="clearHistory"});
            });
            DockPanel.SetDock(clear,Dock.Right);heading.Children.Add(clear);heading.Children.Add(Text("Package jobs",18));packageHistory.Children.Add(heading);
            foreach(var job in jobs)
            {
                var box=new StackPanel();
                var commands=new WrapPanel();
                commands.Children.Add(Button("Open folder",()=>OpenFile(job.Directory)));
                commands.Children.Add(Button("Remove from history",async()=>await ChangeHistoryAsync(new{action="removeHistory",jobId=job.JobId})));
                box.Children.Add(Text($"{job.Name} · {job.Paths.Length} · {job.CreatedAt}",14,localize:false));
                box.Children.Add(new Expander{Header=L10n.Text("Saved paths"),Content=new ListBox{ItemsSource=job.Paths,MaxHeight=150}});
                box.Children.Add(commands);
                packageHistory.Children.Add(Card(box));
            }
        }
        catch(Exception error){if(version==historyVersion){packageHistory.Children.Clear();packageHistory.Children.Add(Text(error.Message,12,"Muted",false));}}
    }

    private void ChangeFileHistory(Action change)
    {
        try{change();selectedLibraryId=null;RenderLibrary();}
        catch(Exception error)when(error is IOException or UnauthorizedAccessException){MessageBox.Show(this,error.Message,"Pivoki");}
    }

    private async Task ChangeHistoryAsync(object request)
    {
        try{await PackageEngine.RequestAsync(request);await RefreshPackageHistoryAsync();}
        catch(Exception error){MessageBox.Show(this,error.Message,"Pivoki");}
    }
}
