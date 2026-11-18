using System.Windows;
using System.Windows.Automation;
using System.Windows.Controls;
using System.Windows.Data;
using Microsoft.Win32;
using Pivoki.Core;

namespace Pivoki.Windows;

internal sealed class PackagesWindow : Window
{
    private readonly PreferencesStore preferences;
    private readonly Action<OutputPackage[]> changed;
    private readonly List<string> inputs;
    private readonly ComboBox packageChoice = new();
    private readonly ComboBox conflicts = new() { ItemsSource=new[]{"Keep both copies","Skip existing outputs"}, SelectedIndex=0 };
    private readonly CheckBox recursive = new() {Content=L10n.Text("Include subfolders")};
    private readonly TextBox outputRoot = new();
    private readonly ListBox selectedInputs = new() {MaxHeight=100};
    private readonly DataGrid table = new() { IsReadOnly=true, AutoGenerateColumns=false, MinHeight=140, MaxHeight=360,
        CanUserAddRows=false, CanUserDeleteRows=false, HeadersVisibility=DataGridHeadersVisibility.Column };
    private readonly ListBox excluded = new(){MaxHeight=150};
    private readonly TextBlock status = new() { TextWrapping=TextWrapping.Wrap, Margin=new Thickness(4,12,4,8) };
    private readonly StackPanel settings = new();
    private readonly Button run, preview, cancel, reveal, edit, delete, pin;
    private OutputPackage[] packages = [];
    private string? planId, resultDirectory, cancelFile;
    private bool working;
    private PackagePlanRow[] approvedRows=[];
    private OutputPackage? Selected => packageChoice.SelectedIndex is var i && i>=0 && i<packages.Length ? packages[i] : null;

    internal PackagesWindow(Window owner, PreferencesStore preferences, IEnumerable<string> sources, string? initialId, int? initialRevision, Action<OutputPackage[]> changed)
    {
        this.preferences=preferences;
        this.changed=changed;
        inputs=sources.Distinct(StringComparer.OrdinalIgnoreCase).ToList();
        Owner=owner;
        Title="Pivoki · "+L10n.Text("Output packages");
        Width=880; Height=810;
        WindowStartupLocation=WindowStartupLocation.CenterOwner;
        Theme.Attach(this);
        var body=new StackPanel{Margin=new Thickness(24)};
        Content=new ScrollViewer{Content=body,VerticalScrollBarVisibility=ScrollBarVisibility.Auto};
        body.Children.Add(settings);
        settings.Children.Add(PackageEditorWindow.Label("Output package",packageChoice));
        settings.Children.Add(packageChoice);
        edit=MainWindow.Button("Edit",()=>Edit(Selected));
        delete=MainWindow.Button("Delete package",async()=>await DeleteAsync());
        pin=MainWindow.Button("Pin to wheel",TogglePin);
        AddButtons(settings,MainWindow.Button("Create package",()=>Edit(null)),edit,delete,pin);
        settings.Children.Add(PackageEditorWindow.Label("Sources",selectedInputs));
        settings.Children.Add(selectedInputs);
        AddButtons(settings,MainWindow.Button("Add files",ChooseFiles),MainWindow.Button("Add folder",ChooseFolder),MainWindow.Button("Remove selected input",()=>{
            if(selectedInputs.SelectedItem is string path){inputs.Remove(path);UpdateInputs();}
        }));
        recursive.Checked+=(_,_)=>InvalidatePlan();
        recursive.Unchecked+=(_,_)=>InvalidatePlan();
        settings.Children.Add(recursive);
        var destination=new DockPanel();
        var browse=MainWindow.Button("Browse…",()=>{
            var picker=new OpenFolderDialog{Title=L10n.Text("Output folder")};
            if(picker.ShowDialog(this)==true)outputRoot.Text=picker.FolderName;
        });
        DockPanel.SetDock(browse,Dock.Right);
        destination.Children.Add(browse);
        destination.Children.Add(outputRoot);
        settings.Children.Add(PackageEditorWindow.Label("Output folder",outputRoot));
        settings.Children.Add(destination);
        outputRoot.TextChanged+=(_,_)=>InvalidatePlan();
        if(preferences.Value.OutputMode=="folder")outputRoot.Text=preferences.Value.OutputFolder;
        settings.Children.Add(PackageEditorWindow.Label("Name conflicts",conflicts));
        settings.Children.Add(conflicts);
        conflicts.SelectionChanged+=(_,_)=>InvalidatePlan();
        preview=MainWindow.Button("Preview output plan",async()=>await PlanAsync());
        run=MainWindow.Primary("Create approved outputs",async()=>await RunAsync());
        cancel=MainWindow.Button("Cancel run",CancelRun);
        reveal=MainWindow.Button("Open result folder",()=>{
            if(resultDirectory is not null)MainWindow.OpenFile(resultDirectory);
        });
        cancel.Visibility=reveal.Visibility=Visibility.Collapsed;
        AddButtons(body,preview,run,cancel,reveal);
        AutomationProperties.SetLiveSetting(status,AutomationLiveSetting.Polite);
        body.Children.Add(status);
        foreach(var (name,property,weight) in new[]{("Source","Source",1.05),("Original target","OriginalTarget",1.2),("Final path","Target",1.35),("State","Status",.55),("Reason","Reason",.85)})
            table.Columns.Add(new DataGridTextColumn{Header=L10n.Text(name),Binding=new Binding(property),Width=new DataGridLength(weight,DataGridLengthUnitType.Star)});
        AutomationProperties.SetName(table,L10n.Text("Output plan"));
        AutomationProperties.SetAutomationId(packageChoice,"PackagePicker");
        AutomationProperties.SetAutomationId(outputRoot,"PackageOutputRoot");
        AutomationProperties.SetAutomationId(preview,"PreviewPackagePlan");
        AutomationProperties.SetAutomationId(run,"RunApprovedPackage");
        AutomationProperties.SetAutomationId(pin,"PinPackage");
        AutomationProperties.SetAutomationId(reveal,"RevealPackageResult");
        AutomationProperties.SetAutomationId(table,"PackagePlanRows");
        body.Children.Add(table);
        body.Children.Add(new Expander{Header=L10n.Text("Skipped inputs and reasons"),Content=excluded});
        AutomationProperties.SetName(excluded,L10n.Text("Skipped inputs and reasons"));
        packageChoice.SelectionChanged+=(_,_)=>InvalidatePlan();
        UpdateInputs();
        Loaded+=async(_,_)=>{
            await LoadPackagesAsync(initialId);
            if(initialId is not null && (Selected?.PackageId!=initialId || Selected.Revision!=initialRevision))
            {
                packageChoice.SelectedIndex=-1;
                status.Text=L10n.Text("This wheel package changed or was removed. Select a current package.");
            }
        };
        Closing+=(_,e)=>{if(working){e.Cancel=true;if(cancelFile is not null)CancelRun();}};
    }

    private static void AddButtons(Panel parent,params Button[] buttons)
    {
        var row=new WrapPanel(); foreach(var button in buttons)row.Children.Add(button);
        parent.Children.Add(row);
    }
    private void UpdateInputs()
    {
        selectedInputs.ItemsSource=inputs.ToArray();
        recursive.IsEnabled=inputs.Any(Directory.Exists);
        InvalidatePlan();
    }
    private void ChooseFiles()
    {
        var picker=new OpenFileDialog{Multiselect=true,Title=L10n.Text("Choose source files")};
        if(picker.ShowDialog(this)==true)AddInputs(picker.FileNames);
    }
    private void ChooseFolder()
    {
        var picker=new OpenFolderDialog{Title=L10n.Text("Process a folder once")};
        if(picker.ShowDialog(this)==true)AddInputs([picker.FolderName]);
    }
    private void AddInputs(IEnumerable<string> paths)
    {
        foreach(var path in paths)if(!inputs.Contains(path,StringComparer.OrdinalIgnoreCase))inputs.Add(path);
        UpdateInputs();
    }
    private void InvalidatePlan()
    {
        planId=resultDirectory=null;approvedRows=[];
        table.ItemsSource=null; excluded.ItemsSource=null;
        status.Text="";
        UpdateButtons();
    }
    private void UpdateButtons()
    {
        if(run is null)return;
        settings.IsEnabled=!working;
        edit.IsEnabled=delete.IsEnabled=pin.IsEnabled=Selected is not null;
        pin.Content=L10n.Text(Selected is not null && preferences.Value.PinnedPackages.Contains(Selected.PackageId)?"Unpin from wheel":"Pin to wheel");
        preview.IsEnabled=!working && Selected is not null && inputs.Count>0 && Path.IsPathFullyQualified(outputRoot.Text);
        run.IsEnabled=!working && planId is not null;
        reveal.Visibility=resultDirectory is null?Visibility.Collapsed:Visibility.Visible;
        cancel.Visibility=cancelFile is null?Visibility.Collapsed:Visibility.Visible;
    }
    private void TogglePin()
    {
        if(Selected is not {} package)return;
        try
        {
            var ids=preferences.Value.PinnedPackages.ToHashSet();
            if(!ids.Remove(package.PackageId))ids.Add(package.PackageId);
            preferences.Save(preferences.Value with{PinnedPackages=ids.Order().ToArray()});
            changed(packages);
            UpdateButtons();
        }catch(Exception error){status.Text=error.Message;}
    }
    private async Task LoadPackagesAsync(string? select)
    {
        try
        {
            working=true; UpdateButtons();
            var reply=await PackageEngine.RequestAsync(new{action="packages"});
            packages=reply.Packages;
            packageChoice.ItemsSource=packages.Select(p=>$"{p.Name} · r{p.Revision}").ToArray();
            var index=Array.FindIndex(packages,p=>p.PackageId==select);
            packageChoice.SelectedIndex=index>=0?index:packages.Length==0?-1:0;
            changed(packages);
            InvalidatePlan();
        }
        catch(Exception error){status.Text=error.Message;}
        finally{working=false;UpdateButtons();}
    }
    private async void Edit(OutputPackage? original)
    {
        var editor=new PackageEditorWindow(this,original);
        if(editor.ShowDialog()==true && editor.Saved is {} saved)await LoadPackagesAsync(saved.PackageId);
    }
    private async Task DeleteAsync()
    {
        if(Selected is not {} package || MessageBox.Show(this,package.Name,L10n.Text("Delete package?"),MessageBoxButton.YesNo,MessageBoxImage.Question,MessageBoxResult.No)!=MessageBoxResult.Yes)return;
        try
        {
            working=true;UpdateButtons();
            await PackageEngine.RequestAsync(new{action="deletePackage",packageId=package.PackageId,revision=package.Revision});
            await LoadPackagesAsync(null);
        }catch(Exception error){status.Text=error.Message;}
        finally{working=false;UpdateButtons();}
    }
    private async Task PlanAsync(PackagePlanRow[]? previous=null)
    {
        if(Selected is not {} package)return;
        InvalidatePlan();
        try
        {
            working=true;UpdateButtons(); status.Text=L10n.Text("Planning outputs…");
            var plan=await PackageEngine.RequestAsync(new{action="plan",packageId=package.PackageId,revision=package.Revision,
                inputs=inputs.ToArray(),outputRoot=outputRoot.Text,recursive=recursive.IsEnabled && recursive.IsChecked==true,
                conflictPolicy=conflicts.SelectedIndex==1?"skip":"keep-both"});
            approvedRows=plan.Rows;
            var previousTargets=previous?.Select(r=>(r.Source,r.Target,r.Status)).ToHashSet();
            bool Changed(PackagePlanRow row)=>previousTargets is not null && !previousTargets.Contains((row.Source,row.Target,row.Status));
            table.ItemsSource=plan.Rows.Select(r=>new {r.Source,r.OriginalTarget,r.Target,Status=L10n.Text(r.Status=="planned"?"Planned":"Skipped"),
                Reason=(Changed(r)?L10n.Text("Changed")+" · ":"")+Reason(r.Reason)}).ToArray();
            excluded.ItemsSource=plan.Skipped.Select(item=>$"{item.Source} — {Reason(item.Reason)}").ToArray();
            var planned=plan.Rows.Where(row=>row.Status=="planned").ToArray();
            if(planned.Length>0)planId=plan.PlanId;
            status.Text=$"{L10n.Text("Eligible inputs")} {plan.InputCount} · " +
                $"{L10n.Text("Outputs")} {planned.Length} · {L10n.Text("Name conflicts")} {plan.ConflictCount} · {L10n.Text("Skipped")} {plan.Skipped.Length+plan.Rows.Length-planned.Length}";
            if(previous is not null)status.Text=L10n.Text("Targets changed. Review and approve the new plan.")+" "+status.Text;
        }catch(Exception error){status.Text=error.Message;}
        finally{working=false;UpdateButtons();}
    }
    private static string Reason(string? reason) => L10n.Text(reason switch
    {
        "kept_both"=>"Keeping both copies", "name_conflict"=>"Name conflict", "unsupported_format"=>"Unsupported format",
        "subfolder_excluded"=>"Subfolders excluded", "output_directory"=>"Output folder excluded", "symbolic_link"=>"Symbolic link",
        "document_bundle"=>"Document bundle", "unreadable"=>"Cannot read this item", "invalid_image"=>"Invalid image", _=>reason??""
    });
    private void CancelRun()
    {
        if(cancelFile is null)return;
        try{File.WriteAllText(cancelFile,"cancel");cancel.IsEnabled=false;status.Text=L10n.Text("Cancelling…");}
        catch(Exception error){status.Text=error.Message;}
    }
    private async Task RunAsync()
    {
        if(planId is not {} approved)return;
        planId=null;
        try
        {
            working=true;
            cancelFile=Path.Combine(Path.GetTempPath(),"pivoki-cancel-"+Guid.NewGuid().ToString("N"));
            cancel.IsEnabled=true;UpdateButtons();status.Text=L10n.Text("Creating approved outputs…");
            var result=await PackageEngine.RequestAsync(new{action="run",planId=approved,cancelFile});
            if(result.Status=="success")
            {
                resultDirectory=result.Directory;
                status.Text=$"{L10n.Text("Saved outputs")} {result.Paths.Length} · {resultDirectory}";
            }
            else status.Text=L10n.Text(result.Status=="cancelled"?"Run cancelled":"Outputs skipped");
        }
        catch(PackageRequestException error)when(error.Code=="replan_required")
        {
            await PlanAsync(approvedRows);
        }
        catch(Exception error){status.Text=error.Message+" "+L10n.Text("Preview a new plan to continue.");}
        finally
        {
            if(cancelFile is not null){try{File.Delete(cancelFile);}catch(IOException){}catch(UnauthorizedAccessException){}}
            cancelFile=null;working=false;UpdateButtons();
        }
    }
}
